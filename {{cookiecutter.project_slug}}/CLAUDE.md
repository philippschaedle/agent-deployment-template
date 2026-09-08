# CLAUDE.md — {{cookiecutter.project_name}}

This file is read automatically by Claude Code and other AI assistants. It contains everything needed to work on this repository without asking for orientation.

## What this project is

**{{cookiecutter.project_name}}** is a Google ADK agent deployed on Vertex AI Agent Engine. It is built from the [agent-deployment-template](https://github.com/{{cookiecutter.github_org}}/agent-deployment-template) cookiecutter.

## Setup (run this once, in order)

Prerequisites: Python {{cookiecutter.python_version}}+, `uv`, Node.js 20+, `gcloud` CLI

```bash
# 1. Install dependencies
make install

# 2. Configure environment
cp .env.example .env
# Edit .env — fill in at minimum: GOOGLE_CLOUD_PROJECT, GOOGLE_API_KEY (for local dev)

# 3. Install pre-commit hooks
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

# 4. Run the agent locally
make dev   # opens http://localhost:8000
```

For GCP deployment (one-time):

```bash
# Deploying locally needs BOTH credential stores. `gcloud auth login` does not
# refresh Application Default Credentials, and `vertexai.init()` reads ADC — so
# logging in only to the CLI fails partway through a deploy with a RefreshError.
gcloud auth login
gcloud auth application-default login

make setup-gcp   # creates SA, enables APIs, generates key for CI
```

## Project layout

```text
agent/
  __init__.py          load_prompt() — reads prompts/prompts.yaml and concatenates .md files
  agent.py             root_agent definition (ADK syntax; this is the entrypoint)
  observability.py     log_event(), @instrument, redact_pii() — see Observability below
  tools/
    __init__.py        re-exports all tools
    example_tools.py   get_current_datetime, web_search (both @instrument-wrapped)
    response_models.py Pydantic schemas for tool return types
prompts/
  prompts.yaml         registry: which .md files load into which agents
  system/
    base.md            always-on identity and style instructions
    safety.md          refusal and safety guidelines
  tasks/
    example_task.md    task-specific instructions (replace with your use case)
deployment/
  config.py            resolve_model() + DeploymentConfig dataclass
  deploy.py            CLI: deploy to Agent Engine (create or update)
  scripts/
    setup_gcp.sh       one-time GCP bootstrap
    read_logs.sh       read this agent's Cloud Logging entries
    read_traces.py     list this agent's Cloud Trace spans
tests/
  unit/                pure function tests — no GCP, no network
  evals/
    promptfoo.yaml     red-team + quality eval config
    provider.py        promptfoo Python provider (runs agent inline)
    datasets/
      golden_set.jsonl reference test cases
```

## Make targets (use these, not raw commands)

| Target | What it does |
|---|---|
| `make dev` | Run agent locally at http://localhost:8000 |
| `make test` | Unit tests with coverage |
| `make test-unit` | Unit tests only, verbose |
| `make test-integration` | Integration tests only |
| `make eval` | promptfoo red-team evaluation |
| `make lint` | ruff lint check |
| `make format` | ruff format |
| `make typecheck` | pyright |
| `make pre-commit` | All pre-commit hooks |
| `make deploy-dev` | Deploy to Agent Engine (dev) |
| `make deploy-prod` | Deploy to Agent Engine (prod) |
| `make rollback REF=<tag> [ENV=prod\|dev]` | Redeploy a previous git ref against the existing Agent Engine resource |
| `make health-check` | Standalone smoke test against the deployed Agent Engine resource (no fresh deploy) |
| `make logs` | Read this agent's Cloud Logging entries |
| `make traces` | List this agent's Cloud Trace spans |
| `make setup-gcp` | One-time GCP bootstrap |
| `make setup-monitoring` | One-time Cloud Monitoring dashboard + alert policy bootstrap |
| `make clean` | Remove caches, coverage output and build artefacts |
| `make help` | List every target with its description |

## How to add a tool

1. Write the function in `agent/tools/example_tools.py` (or create a new file in `agent/tools/`)
2. Add type annotations and a docstring — ADK uses these to build the tool schema
3. Export from `agent/tools/__init__.py`
4. Add to `tools=[...]` in `agent/agent.py`
5. Add unit tests in `tests/unit/test_tools.py`

```python
# Example tool signature
def my_tool(param: str) -> str:
    """One-line description used by the model to decide when to call this tool.

    Args:
        param: Description of the parameter.

    Returns:
        Description of the return value.
    """
    ...
```

Wrap new tools with `@instrument` from `agent/observability.py` (see Observability below) the same
way `get_current_datetime` and `web_search` are — `functools.wraps` keeps ADK's tool-schema
introspection working unchanged, verified by comparing `FunctionTool` declarations before/after.

## Observability

`agent/observability.py` provides structured JSON logging, applied at the boundary this project
actually controls — tool calls — rather than `Runner.run_async`, which Agent Engine's managed
runtime drives internally and which our code never touches in production:

- **`@instrument`** — wraps a tool function (sync or async) and logs `<name>.start`,
  `<name>.end` (with `duration_ms`), or `<name>.error` (with the exception message) as JSON.
  Already applied to both tools in `agent/tools/example_tools.py`.
- **`log_event(event_type, fields, severity="INFO")`** — emit one structured JSON line for
  anything else worth recording. `CloudLoggingHandler` parses that JSON line into a
  `jsonPayload`, and the Python log level (chosen from `severity`) sets the LogEntry's own
  severity field, so `severity=ERROR` is filterable directly in Logs Explorer.
- **`redact_pii(value)`** — recursively redacts emails, SSNs, and credit-card-shaped numbers from
  strings, dicts, and lists. `log_event` and `@instrument` both redact fields before logging them,
  but it's a defence-in-depth measure, not a substitute for not logging sensitive fields in the
  first place.
- **`log_model_usage(event)`** — logs token counts from an ADK event's `usage_metadata`, for code
  that iterates the event stream itself (the promptfoo eval provider does); not reachable from
  Agent Engine's own request path for the same reason `@instrument` doesn't wrap `Runner.run_async`.

### Destinations

**Logs need no configuration.** Agent Engine forwards container stdout/stderr to Cloud Logging
under `aiplatform.googleapis.com/reasoning_engine_stdout` and `..._stderr`, and parses a JSON
stdout line into a structured `jsonPayload`. `make logs` reads exactly those, scoped to this
agent by `reasoning_engine_id` — the log names are shared by every reasoning engine in the
project.

**Traces do need configuration**, because nothing forwards spans. `deployment/deploy.py` sets two
variables on the deployed resource:

| Variable | Effect |
|---|---|
| `CLOUD_TRACE_ENABLED` | Configure an OpenTelemetry tracer exporting to Cloud Trace; every `@instrument`ed call becomes a span named after the function. These are **child** spans — ADK wraps each request in an `invoke_workflow` root span — so `make traces` lists roots only; use `read_traces.py --spans` to expand them |
| `OTEL_EXPORTER_GCP_TRACE_PROJECT_ID` | The project to export to. **Not optional** — without it the exporter falls back to `google.auth.default()`, which resolves no project inside the Agent Engine container, and every export fails with `INVALID_ARGUMENT: Invalid project id in name!` |

Tracing is off by default so a local `make dev` writes only to stdout and needs no credentials;
export `CLOUD_TRACE_ENABLED=true` to opt in locally. Telemetry never breaks a tool call: a missing
library or unresolvable credentials is reported once on stderr and the tool runs on.

> **If application logs seem to be missing, check the project's log sink first.**
> A disabled `_Default` sink discards every non-audit entry however it was written — including
> direct `gcloud logging write` calls — so it looks exactly like broken instrumentation. This
> cost a full debugging session: the conclusion was "Agent Engine doesn't forward stdout", the
> fix was a Cloud Logging client library, and the truth was one flag on a sink.
>
> ```bash
> gcloud logging sinks describe _Default --project=$GOOGLE_CLOUD_PROJECT   # disabled: true is the bug
> gcloud logging sinks update _Default --no-disabled --project=$GOOGLE_CLOUD_PROJECT
> ```
>
> Sink changes take a few minutes to propagate, and entries written in the meantime are lost.

### Log fields

Every event is one JSON object with these keys (exact set depends on which function emitted it):

| Field | Emitted by | Description |
|---|---|---|
| `severity` | all | `INFO` or `ERROR`; a Cloud Logging reserved field, filterable as `severity=ERROR` |
| `agent_name` | all | Always `root_agent`, in every project generated from this template — so it does **not** identify one agent in a shared project. `read_logs.sh` scopes by `reasoning_engine_id` instead |
| `event` | all | Event name: `<tool>.start` / `.end` / `.error`, or `model.usage` |
| `duration_ms` | `@instrument` | Wall-clock time for the call |
| `outcome` | `@instrument` (`.end`) | Always `success` — failures are a separate `.error` event instead |
| `error` | `@instrument` (`.error`) | `str(exception)` |
| `args`, `kwargs` | `@instrument` (`.start`) | The call's arguments, PII-redacted |
| `prompt_tokens`, `candidates_tokens`, `total_tokens` | `log_model_usage` | From the ADK event's `usage_metadata` |

See [Cloud Logging query examples](README.md#cloud-logging-query-examples) in `README.md` for
filters using these fields.

## How to modify prompts

1. Edit or add a `.md` file in `prompts/system/` or `prompts/tasks/`
2. If adding a new file, register it in `prompts/prompts.yaml` under the relevant agent
3. Run `make dev` and verify the agent behaves as expected
4. Add a promptfoo test case in `tests/evals/promptfoo.yaml` if the change affects safety or key behaviour

## How to add a sub-agent

1. Add an entry in `prompts/prompts.yaml` for the new agent name
2. Define the agent in `agent/agent.py` using standard ADK `Agent()` syntax
3. Wire it to `root_agent` via `sub_agents=[new_agent]` (ADK handles routing)

No custom classes, no inheritance — pure ADK syntax only.

## Multi-provider model selection

Set `MODEL_PROVIDER` in `.env`:

| Value | Model | Requires |
|---|---|---|
| `google` (default) | Gemini 2.5 Pro | `GOOGLE_API_KEY` (local) or ADC (GCP) |
| `anthropic` | Claude Opus 4.8 via LiteLLM | `ANTHROPIC_API_KEY` |
| `openai` | GPT-4o via LiteLLM | `OPENAI_API_KEY` |
| `litellm` | Set `LITELLM_MODEL` | depends on model |

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Deploy only | — | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | Deploy only | `europe-west1` | Vertex AI region |
| `GCS_STAGING_BUCKET` | No | `gs://$GOOGLE_CLOUD_PROJECT-agent-staging` | Override only if you renamed the bucket; the `gs://` scheme is optional |
| `AGENT_ENGINE_RESOURCE_NAME` | No | — | Existing resource to update (omit = create new) |
| `AGENT_ENGINE_SERVICE_ACCOUNT` | No | `agent-engine-sa@$GOOGLE_CLOUD_PROJECT…` | Override only if you renamed the SA — see [Runtime identity](#runtime-identity) |
| `CLOUD_TRACE_ENABLED` | No | off | Export a Cloud Trace span per tool call; `deploy.py` sets it on the deployed agent |
| `OTEL_EXPORTER_GCP_TRACE_PROJECT_ID` | With tracing | — | Project the span exporter writes to; `deploy.py` sets it from `GOOGLE_CLOUD_PROJECT` |
| `MODEL_PROVIDER` | No | `google` | Provider selection |
| `LITELLM_MODEL` | If provider=litellm | — | Full LiteLLM model string |
| `ANTHROPIC_API_KEY` | If provider=anthropic | — | |
| `OPENAI_API_KEY` | If provider=openai | — | |
| `GOOGLE_API_KEY` | Local dev | — | Not needed on GCP (uses ADC) |
| `SERPAPI_API_KEY` | No | — | Enables live web search; omit for stub |

## Pre-commit (required — always fix before committing)

```bash
make pre-commit   # runs all hooks
```

- If ruff fails: run `make format` then `make lint` — ruff autofixes most issues
- If pyright fails: fix the type errors it reports
- If detect-secrets fails: make sure you have not committed credentials
- **Never use `git commit --no-verify`** — this bypasses safety checks

## Conventional commits (enforced twice — locally and in CI)

Format: `type(scope): description`

Allowed types: `build`, `bump`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`,
`revert`, `style`, `test`.

```text
feat(agent): add calendar lookup tool
fix(prompts): correct safety guidelines for PII handling
chore(deps): bump google-adk to 1.1.0
docs(readme): update deployment instructions
test(evals): add promptfoo test for jailbreak via roleplay
refactor(deployment): simplify config dataclass
```

Two things enforce this, and both matter:

- The **`commit-msg` hook** (commitizen) rejects non-conforming *commit messages* locally.
- **`lint-pr.yml`** checks the **PR title** in CI. This is not redundant: a squash merge
  discards the branch's commit messages and uses the PR title as the subject of the commit
  that lands on `main` — the one `cz bump` reads to build `CHANGELOG.md`. The local hook is
  also bypassable with `--no-verify` or by committing through the GitHub web UI.

Both accept the same set of types, so a message the hook accepts is always a valid PR title.

## CHANGELOG (update for every user-facing change)

Add an entry under `[Unreleased]` in `CHANGELOG.md` before committing. Use Keep a Changelog format:

```markdown
## [Unreleased]

### Added
- Calendar lookup tool powered by Google Calendar API

### Fixed
- Web search stub now includes query in snippet for easier local debugging
```

Run `cz bump` (via `uv run cz bump`) to cut a release and move unreleased entries to a dated section.

## Claude Code slash commands

| Command | What it does |
|---|---|
| `/deploy` | Runs `make deploy-prod` and reports the resource name |
| `/eval` | Runs `make eval` and summarises results |
| `/logs` | Runs `make logs` and streams Cloud Logging output |

## Rollback

Agent Engine deploys are **source-based** (`agent_engines.create`/`update` pickles `root_agent`
directly) — there is no container image digest to pin a rollback to. Rolling back means checking
out a previous git ref and redeploying it against the *existing* `AGENT_ENGINE_RESOURCE_NAME`,
which `deploy.py` updates in place rather than creating a new resource.

**Locally:**

```bash
make rollback REF=v1.2.0                # redeploys v1.2.0 to prod
make rollback REF=v1.2.0 ENV=dev        # redeploys v1.2.0 to dev
```

This checks out `REF`, runs `deployment/deploy.py --env <ENV>`, and restores your original branch
afterwards regardless of whether the deploy succeeds.

**Via GitHub Actions:** manually trigger the `deploy.yml` workflow (Actions tab → Deploy → Run
workflow) and set the `ref` input to the tag, branch, or SHA you want to roll back to, alongside
the `environment` input. Leaving `ref` empty deploys the triggering ref as usual.

After either path, run `make health-check` to confirm the resource is responding — useful when
you want to verify a rollback worked without triggering another deploy.

## Health check

`deployment/scripts/health_check.py` sends a message to the Agent Engine resource named by
`AGENT_ENGINE_RESOURCE_NAME` and requires at least one event back — the same smoke test
`deploy.py` runs right after deploying, but runnable standalone against an already-deployed
resource:

```bash
make health-check                                                    # uses .env
uv run python deployment/scripts/health_check.py --message "hello"   # customize the ping
```

Exits `0` on success, `1` on failure, so it's safe to gate CI or a cron job on. `deploy.yml` runs
it as its own step right after deploying, reading the resource name from `.agent_engine_resource`
so it works whether that deploy created a new resource or updated an existing one.

## Runtime identity

Two identities are involved in a deploy, and they are not the same thing:

| Identity | What it is |
|---|---|
| The **deployer** | Whoever runs `deploy.py` — your user account locally, or `agent-engine-sa` via `GCP_SA_KEY` in `deploy.yml` |
| The **runtime** | Whoever the deployed agent runs *as* when it serves a request |

`agent_engines.create`/`update` accept a `service_account` parameter, and **if it is omitted the
runtime is the project's shared Reasoning Engine Service Agent**
(`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re...`), not the SA `setup_gcp.sh` creates. An
earlier version of this template omitted it, which made the least-privilege story in these docs
untrue: `agent-engine-sa`'s grants applied only to the *caller* of `deploy.py`, while the actual
runtime permissions came from a service agent nobody had configured.

`deploy.py` now always passes a `service_account`. You do not configure it: the SA name is fixed
by `setup_gcp.sh`, so `DeploymentConfig` derives `agent-engine-sa@$GOOGLE_CLOUD_PROJECT` from the
project id. `AGENT_ENGINE_SERVICE_ACCOUNT` exists only to override that if you renamed the SA. The
staging bucket is derived the same way, for the same reason.

> **Upgrading an existing project — breaking.** A project generated before this change deploys
> with no `service_account`, so its agent runs as the shared service agent. After a `cruft update`
> it starts passing one, and the next deploy fails with `PermissionDenied` on `actAs` until the
> binding below exists.
>
> **Migration:** re-run `make setup-gcp ENV=<env>` before your next deploy — it adds the binding
> and is safe to re-run. Note the first deploy afterwards also *changes the running agent's
> identity*, so confirm the SA holds the roles the agent needs at runtime.
>
> Setting `AGENT_ENGINE_SERVICE_ACCOUNT=""` is not an escape hatch — an empty value falls back to
> the derived SA. To stay on the old behaviour, pin the template to the previous version instead
> of updating.

### The actAs prerequisite

Passing a real runtime identity makes an IAM permission real too: whoever deploys needs
`roles/iam.serviceAccountUser` **on that service account** for Vertex to accept it. The old
behaviour needed none, because it never passed a service account at all.

`setup_gcp.sh` grants it to two principals, which covers both normal deploy paths:

| Principal | Why |
|---|---|
| `agent-engine-sa` itself | how CI authenticates (`GCP_SA_KEY` in `deploy.yml`) |
| whoever runs the bootstrap | the likely local deployer — picked up from `gcloud config get-value account` |

Teammates who also deploy from their own machines need adding by hand:

```bash
gcloud iam service-accounts add-iam-policy-binding agent-engine-sa@$GOOGLE_CLOUD_PROJECT.iam.gserviceaccount.com \
  --member="user:them@example.com" --role=roles/iam.serviceAccountUser --project=$GOOGLE_CLOUD_PROJECT
```

Without the grant, the failure is a `PermissionDenied` on `actAs` that arrives *after* the agent
has been pickled and uploaded — so if you see that mid-deploy, this is why.

To check what a deployed resource actually runs as, read its `serviceAccount` field — `(none set)`
means it is on the shared service agent.

## Monitoring & alerting

Vertex AI Agent Engine emits platform-level metrics automatically under the
`aiplatform.googleapis.com/ReasoningEngine` monitored resource — no instrumentation needed for
these (unlike the app-level structured logging in `agent/observability.py`):

| Metric | Description |
|---|---|
| `reasoning_engine/request_count` | Request count, labeled by `response_code` / `response_code_class` |
| `reasoning_engine/request_latencies` | Request latency distribution (ms) |
| `reasoning_engine/cpu/allocation_time` | Container CPU allocation time |
| `reasoning_engine/memory/allocation_time` | Container memory allocation time |

`deployment/monitoring/` builds a dashboard and two alert policies on top of these, applied via
plain `gcloud` (consistent with `setup_gcp.sh` — this template uses no Terraform):

- `dashboard.json` — request count by response code, p50/p95/p99 latency, CPU/memory allocation
- `alerting/error_rate.json` — 5xx response rate > 5% over 5 minutes (ratio condition via
  `denominatorFilter`, matching total request count)
- `alerting/latency_p95.json` — p95 request latency > 3000ms over 5 minutes

```bash
make setup-monitoring                                    # dashboard + alerts, no notifications
ALERT_EMAIL=oncall@example.com make setup-monitoring      # + email notification channel
SLACK_CHANNEL="#agent-alerts" SLACK_BOT_TOKEN=xoxb-... \
  make setup-monitoring                                   # + Slack notification channel
```

Safe to re-run: it updates the existing dashboard/policies/channels by display name instead of
creating duplicates. Editing `dashboard.json` and re-running is the intended way to change the
dashboard. (The Dashboards API rejects an update without the dashboard's current `etag`, which a
checked-in config file cannot carry, so `setup_monitoring.sh` reads the live `etag` and injects it
before updating.) Run once per GCP project (dev and prod separately, same as `setup-gcp`).
Preview a dashboard change first with `gcloud monitoring dashboards create --config-from-file=
deployment/monitoring/dashboard.json --validate-only --project=$GOOGLE_CLOUD_PROJECT`.

**Not covered here:** rate-limit/quota alerting. Vertex AI doesn't expose a per-agent quota metric
to threshold on — configure that separately via Cloud Console → IAM & Admin → Quotas → Create
Alert.

## CI/CD overview

| Workflow | Trigger | What it checks |
|---|---|---|
| `ci.yml` | push + PR | lint, format, typecheck, unit tests, combined-suite coverage |
| `lint-pr.yml` | PR opened/edited | PR title is a valid conventional commit |
| `security.yml` | push to main + weekly | CodeQL, pip-audit CVEs, secret scan |
| `eval.yml` | PR to main | promptfoo red-team (90% pass threshold) |
| `deploy.yml` | push to main | deploys to Agent Engine prod, then runs a standalone health check |
| `cruft-check.yml` | push + PR + weekly | non-blocking: warns if `cruft update` is available from the template |

## Required GitHub Environments

`deploy.yml`'s job targets a GitHub Environment named `dev` or `prod` (Settings → Environments →
New environment), matching its `environment` `workflow_dispatch` input — a plain push to `main`
defaults to `prod`. Each environment should point at its own GCP project, so dev and prod need
their own **Environment secrets/variables** — not repository-level ones, which would make both
environments share the same credentials:

| Name | Kind | Scope | Description |
|---|---|---|---|
| `GCP_SA_KEY` | Secret | Per environment (`dev`, `prod`) | Base64 service-account key, printed by `make setup-gcp ENV=<dev\|prod>` |
| `GOOGLE_CLOUD_PROJECT` | Secret | Per environment | That environment's GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | Variable | Per environment | Vertex AI region |
| `MODEL_PROVIDER` | Variable | Per environment | `google` \| `anthropic` \| `openai` \| `litellm` |
| `AGENT_ENGINE_RESOURCE_NAME` | Variable | Per environment | Existing resource to update; set after that environment's first deploy |
| `GCS_STAGING_BUCKET` | Variable | Per environment | Optional — derived from the project id unless you renamed the bucket |
| `AGENT_ENGINE_SERVICE_ACCOUNT` | Variable | Per environment | Optional — derived from the project id unless you renamed the SA |
| `GOOGLE_API_KEY` | Secret | Repository-level | Used only by `eval.yml` (promptfoo), not per-environment  <!-- pragma: allowlist secret --> |

Bootstrap each environment's GCP project with `make setup-gcp ENV=dev` / `make setup-gcp
ENV=prod` (see [setup_gcp.sh](deployment/scripts/setup_gcp.sh)) — it prints exactly which secret
or variable to add and to which environment.
