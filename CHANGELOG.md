# Changelog

All notable changes to this cookiecutter template are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — see
[Template Versioning](CLAUDE.md#template-versioning) in `CLAUDE.md` for what bumps count as
MAJOR/MINOR/PATCH and how releases are tagged.

## [Unreleased]

### Changed

- **Retracted: "the observability layer has no destination in production."** An earlier draft of
  this entry claimed `@instrument`, `log_event` and `redact_pii` wrote to a void once deployed,
  because Agent Engine did not forward container stdout the way Cloud Run does, and added a
  `google-cloud-logging` client handler to fix it. **That diagnosis was wrong and the change has
  been reverted.** Agent Engine forwards stdout correctly, under
  `aiplatform.googleapis.com/reasoning_engine_stdout`.

  The evidence that produced the wrong conclusion — zero application logs after a confirmed
  production tool call — was caused by the **`_Default` log sink being disabled in the GCP
  project**, which discards every non-audit entry however it is written. The tell was that
  *nothing* in that project had logged anything for 30 days, across five agents from three
  teams, and that a direct `gcloud logging write` was accepted and then unreadable. With the
  sink enabled, every event arrived twice — once via stdout, once via the added handler — which
  is what proved the handler redundant. It and the `google-cloud-logging` dependency are gone,
  and the stdout design the template started with stands. `read_logs.sh` and `CLAUDE.md` now
  point at the sink as the first thing to check when logs go missing.

- **BREAKING: deployed agents now run as `agent-engine-sa`, not the shared Reasoning Engine
  Service Agent.** This is the visible half of the runtime-identity fix below, and it changes
  the behaviour of existing generated projects on `cruft update`: `deploy.py` now always passes
  a `service_account`, where before it passed none. The next deploy after an update fails with
  `PermissionDenied` on `actAs` until the new IAM binding exists.

  **Migration:** re-run `make setup-gcp ENV=<env>` before the next deploy — it adds the binding
  and is safe to re-run. Then check that `agent-engine-sa` holds whatever roles the agent needs
  at runtime, because the identity it runs under genuinely changes. To defer, pin the template
  to the previous release rather than updating.

### Fixed

- **`make logs` and `make traces` queried the wrong things, and tracing never worked at all.**
  `read_logs.sh` filtered on `resource.type="aiplatform.googleapis.com/Endpoint"`, which is not
  what an Agent Engine deployment uses. The real destination — confirmed against a live
  deployment — is `aiplatform.googleapis.com/reasoning_engine_stdout` and `..._stderr`, where
  Agent Engine forwards container stdout/stderr and parses each JSON line into a structured
  `jsonPayload`. The script now reads those, scoped by `reasoning_engine_id`, because the log
  names are shared by every reasoning engine in the project and `jsonPayload.agent_name` is
  `root_agent` in every project generated from this template.

  `read_traces.sh` was worse: it printed a **Cloud Logging** filter expression, labelled it a
  Cloud Trace filter, and then opened the console — it never queried an API, so it could not
  fail visibly. It is replaced by `read_traces.py`, which calls the Cloud Trace v1 API (there is
  no `gcloud trace` command group) with `--since` / `--limit` / `--filter`, and whose argument
  handling and rendering are unit-tested.

  Tracing itself is new: nothing in the template had ever configured an exporter, so `make
  traces` was aspirational. `@instrument` now opens an OpenTelemetry span per call, exported to
  Cloud Trace, enabled per deployment by `CLOUD_TRACE_ENABLED`. The exporter is also passed
  `OTEL_EXPORTER_GCP_TRACE_PROJECT_ID` explicitly, which is **not** optional: left to its own
  `google.auth.default()` fallback it resolves no project inside the Agent Engine container and
  fails every export with `INVALID_ARGUMENT: Invalid project id in name!`. Both are off by
  default so a local `make dev` stays offline and free.

- **`make setup-monitoring` could not be re-run.** The second run failed with
  `INVALID_ARGUMENT: Update Dashboard should specify a non empty etag`: the script finds the
  existing dashboard by display name and calls `dashboards update --config-from-file`, but the
  API requires the dashboard's current `etag` and a checked-in `dashboard.json` cannot carry
  one. That broke the only workflow the template offers for changing a dashboard — edit
  `dashboard.json`, re-run — while the generated `CLAUDE.md` claimed re-running was safe. The
  script now reads the live `etag` and injects it into a temporary copy of the config before
  updating, and fails loudly if the `etag` cannot be read rather than letting the API reject
  the call.
- **Deployed agents never ran as the service account `setup_gcp.sh` provisions.**
  `agent_engines.create`/`update` accept a `service_account` parameter and `deploy.py` did not
  pass it, so — as the SDK documents — every agent deployed by this template ran as the
  project's shared Reasoning Engine Service Agent, confirmed by reading `spec.service_account`
  off a live deployment. The effect was that `setup_gcp.sh`'s central act was largely
  theatre: it created `agent-engine-sa` and granted it `aiplatform.user`,
  `logging.logWriter` and `cloudtrace.agent`, and the running agent never assumed that
  identity — those grants only ever applied to the *caller* of `deploy.py`, while the real
  runtime permissions came from a service agent nobody had configured. The least-privilege
  story in the generated docs therefore described something that was not happening.
  `deploy.py` now passes `service_account=$AGENT_ENGINE_SERVICE_ACCOUNT` when that variable is
  set, and only when set, so `cruft update` cannot silently retarget the identity of a
  resource created without one. `deploy.yml` passes the variable through, and a new "Runtime
  identity" section in the generated `CLAUDE.md` spells out the difference between the deployer
  and the runtime.

  The service account is **derived, not configured**: its name is fixed by
  `setup_gcp.sh`, so `DeploymentConfig` builds `agent-engine-sa@$GOOGLE_CLOUD_PROJECT` from the
  project id, and `AGENT_ENGINE_SERVICE_ACCOUNT` survives only as an override for a renamed SA.
  Restating a derived value in `.env` is just an opportunity for the two to drift. The staging
  bucket now works the same way (`gs://$GOOGLE_CLOUD_PROJECT-agent-staging`), which also settles
  an old inconsistency: `setup_gcp.sh` printed it without the `gs://` scheme while the docs showed
  it with one — either spelling is now accepted and normalised.

  Passing a real identity makes an IAM permission real too — the deployer needs
  `roles/iam.serviceAccountUser` on that SA, where the old behaviour needed nothing — so
  `setup_gcp.sh` grants it to both principals that actually deploy: the SA itself (how CI
  authenticates) and whoever runs the bootstrap, read from `gcloud config get-value account`
  and prefixed `user:` or `serviceAccount:` as appropriate. Granting only the former would
  leave a first local `make deploy-dev` failing with `PermissionDenied` on `actAs` *after*
  pickling and uploading the agent, with the fix buried in a doc sentence.

  Still open, deliberately: `setup_gcp.sh` continues to mint a user-managed service-account
  key on every run and never revokes it. Moving CI to Workload Identity Federation is tracked
  separately, since it changes how `deploy.yml` authenticates.

- **Local deploys needed `gcloud auth application-default login` and no generated doc said
  so.** `vertexai.init()` reads Application Default Credentials, which `gcloud auth login` does
  not refresh — so a correctly logged-in user got a `RefreshError` partway through their first
  `make deploy-dev`, after the agent had already been pickled and uploaded. Both commands are
  now in the deploy prerequisites in `README.md`, `CLAUDE.md` and `AGENTS.md`.
- **Three real make targets were undocumented.** `make test-integration`, `make clean` and
  `make help` exist in the generated `Makefile` but appeared in no table, so the documented
  target list was a subset of the real one. Added to `CLAUDE.md`.

- **A renamed staging bucket was silently ignored in CI.** `setup_gcp.sh` now prints
  `GCS_STAGING_BUCKET` as an optional GitHub Environment *variable*, alongside
  `AGENT_ENGINE_SERVICE_ACCOUNT`, but `deploy.yml` still read it from `secrets`. Anyone who
  renamed their bucket and followed those instructions got an empty value, and `deploy.py` fell
  back to the derived `gs://$GOOGLE_CLOUD_PROJECT-agent-staging` without saying so. `deploy.yml`
  now reads `vars.GCS_STAGING_BUCKET` in both the deploy and health-check steps. A bucket name is
  not a credential, and storing it as a secret also meant GitHub masked it as `***` in the deploy
  log — exactly where you want to read it when a staging upload fails.

  **Migration:** only affects projects that set `GCS_STAGING_BUCKET` at all. If yours is the
  default `<project>-agent-staging`, delete the secret and change nothing else. If you renamed the
  bucket, move the value from an Environment secret to an Environment variable of the same name.

  `AGENTS.md`'s environment table was also still describing the pre-derivation world — it listed
  `GCS_STAGING_BUCKET` as required, omitted `AGENT_ENGINE_SERVICE_ACCOUNT`, `CLOUD_TRACE_ENABLED`,
  `OTEL_EXPORTER_GCP_TRACE_PROJECT_ID` and `LITELLM_MODEL`, and named a secret set that no longer
  matches `deploy.yml`. It now agrees with `CLAUDE.md` and `README.md`.

- **`cruft create` left every generated project with a dirty working tree.**
  `hooks/post_gen_project.py` writes `.cruft.json` and commits it, and then cruft rewrites
  the same file after the hook returns — so the documented `cruft create gh:org/repo` flow
  produced a project whose first `git status` showed a modification its author never made,
  ready to be swept into their next commit. Plain `cookiecutter` never showed it, because
  cruft is not involved there, which is why earlier testing missed it. Two differences had
  to be closed, both verified necessary by byte-comparing the hook's output against
  cruft's own `json_dumps` for the same answers: cruft appends `_commit` to the context
  (added here only when cruft supplies it, so plain-cookiecutter output is unchanged), and
  cruft passes `ensure_ascii=False`, so a non-ASCII author name such as `Schädle` was
  written escaped by the hook and unescaped by cruft. The two files are now byte-identical.
- **`security.yml`'s CodeQL job failed permanently on private repositories.** Code scanning
  is free on public repos but needs GitHub Advanced Security on private ones, and the job
  had no guard — so every push to `main` in a private generated project produced a red
  `CodeQL Analysis` check forever, which is worse than no job at all because it teaches a
  team to ignore red CI. Confirmed on a real private repo:
  `Code scanning is not enabled for this repository`. Testing visibility would have been
  the wrong fix — private + Advanced Security should still run CodeQL. A small
  `code-scanning-available` job now probes `GET /code-scanning/alerts` and gates CodeQL on
  the result: the API returns 403 when code scanning is unavailable and 404 (`no analysis
  found`) or 200 when it is, so only a 403 disables it. Verified against both real cases —
  403 on a private repo without GHAS, 404 on a public one. CodeQL is then *skipped* rather
  than failed, and the step summary explains why; `Dependency CVE Audit` and `Secret Scan`
  are unaffected and still run everywhere.
- **Generation failed outright on any machine without a configured git identity** —
  `hooks/post_gen_project.py`'s `git commit` exited 128 with `fatal: empty ident name`, and
  because cookiecutter treats a failing post-gen hook as fatal, it then deleted everything
  it had just produced: no project at all, not merely an uncommitted one. This hit CI
  runners, containers and freshly-imaged laptops — anywhere git cannot guess an identity
  from the OS user — and was introduced by the initial-commit fix in the previous release.
  It went unnoticed because a developer machine with a global `user.name` never reproduces
  it. Found on the first real CI run of `validate-template.yml`, where all four matrix
  variants failed identically. The hook now falls back to the cookiecutter `author_name` /
  `author_email` written to the **new repo's local config only** (an existing global or
  system identity is left untouched), and the commit itself is no longer fatal — a
  generated-but-uncommitted project is recoverable in one command, which the warning now
  prints.
- **Generating with `python_version=3.12` produced a project that failed its own
  `ruff check` on the very first CI run.** With `target-version = "py312"`, ruff's `UP047`
  fires on `agent/observability.py`'s `def instrument(func: F) -> F`, demanding PEP 695
  generics (`def instrument[F](...)`) — 3.12+ syntax the template source cannot use,
  because the same source must also render and parse under Python 3.11. One of the two
  allowed values of a cookiecutter variable therefore shipped a broken project.
  `UP046`/`UP047` are now in the generated `pyproject.toml`'s ruff `ignore` list, with a
  comment explaining that they are safe to drop if 3.11 support is not wanted.
- **Six template source files were not `ruff format` clean, so `ci.yml`'s
  `lint-format-typecheck` job failed on the first PR of every generated project.** The
  generated `ci.yml` runs `uv run ruff format --check .`, but nothing in this template repo
  ever format-checked the generated tree: `make validate` ran only `ruff check`, and ruff
  cannot be pointed at the template sources in place because
  `{{cookiecutter.project_slug}}/pyproject.toml` has unrendered Jinja in `requires-python`
  (`Failed to parse version: >={{cookiecutter.python_version}}`). Reformatted
  `deployment/config.py`, `tests/integration/test_agent_runner.py`, and four
  `tests/unit/test_*.py` files.
- Freshly generated projects failed their own `make pre-commit` before their author had
  written a line of code, on two hooks:
  - `end-of-file-fixer` rewrote `LICENSE` — un-trimmed Jinja block tags left the rendered
    file with both a leading blank line and a trailing one. The `{% if %}`/`{% elif %}`
    tags now sit on the same line as the license text they introduce (preserving the
    Apache banner's indentation, which a `-%}` strip marker would have eaten), and
    `{% endif -%}` absorbs the template's own trailing newline.
  - `detect-secrets` flagged `.cruft.json` as a `HexHighEntropyString` — it holds the
    template's 40-character git SHA. That SHA differs per generated project and changes on
    every `cruft update`, so it cannot be pinned in `.secrets.baseline`; the file is now
    excluded from the hook. Previously masked in testing because plain
    `cookiecutter . --no-input` records an empty `commit` field, while the documented
    `cruft create gh:org/repo` flow records a real SHA and always tripped it.
- Generated `ci.yml`'s `test` and `integration-test` jobs each ran `pytest` against only
  `tests/unit` or only `tests/integration`, but both were still held to the project-wide
  `--cov-fail-under=75` bar (`pyproject.toml`) — a bar neither suite was ever meant to
  clear alone. `integration-test` failed this way on every PR, deterministically (66%
  coverage from `tests/integration` alone vs. the 75% requirement), regardless of code
  quality. Both jobs now run with `--no-cov`; a new `coverage` job runs `tests/unit` and
  `tests/integration` together in one invocation and enforces the 75% bar against their
  combined coverage (96% in the template's own example agent) — the check CI was always
  meant to be doing.
- Generated `eval.yml` pinned Node 20 for the promptfoo evaluation step, but promptfoo
  requires Node >=22.22.0 — `eval.yml` failed on every PR with an `EBADENGINE` error before
  ever reaching the actual evaluation. Bumped to Node 22.
- Generated `eval.yml` passed `--ci` to `promptfoo eval`, which is not a recognized flag on
  current promptfoo (`error: unknown option '--ci'`, confirmed against its own `--help`
  output) — every generated project's eval job failed on every PR before attempting any
  evaluation, independent of the Node-version fix above. Removed `--ci` and added
  `-o output.json` so the existing "Upload results" step has a file to upload.
- **The eval CI job likely never actually worked, for any generated project, until now.**
  `eval.yml` ran `npx --yes promptfoo@latest eval ...` bare, with no `uv run` wrapper.
  promptfoo's `python:provider.py` provider spawns its own Python worker to import
  `tests/evals/provider.py`, which needs this project's dependencies (`python-dotenv`,
  `google-adk`, ...) — installed by `uv sync` into `.venv`, not into the bare system Python
  `actions/setup-python` puts on `PATH`. Confirmed via a real CI run with a valid
  `GOOGLE_API_KEY`: all 20 test cases failed with `ModuleNotFoundError: No module named
  'dotenv'`, before ever reaching a real model call. `make eval`'s local path
  (`tests/evals/run_eval.py`) never hit this, since it's invoked via `uv run python ...`,
  which activates `.venv` for the whole subprocess tree it spawns (`npx` → node →
  promptfoo's Python worker) — CI's direct `npx` invocation had no equivalent activation.
  Fixed by wrapping the CI invocation in `uv run` too, matching the working local path.
- **Security-relevant:** `eval.yml` relied on `promptfoo eval`'s own exit code to gate the
  PR check, but verified empirically that promptfoo exits `0` even when every test case
  errors out (100% errors, 0% successes reproduced a clean exit 0 locally) — e.g. an
  invalid or expired `GOOGLE_API_KEY` would make every eval case error, and the `Eval`
  check would still report green. Since this gate covers the `safety_injection`/
  `safety_pii` datasets, a silent false-pass here is a real regression, not a minor gap.
  Added an explicit "Enforce evaluation results" step that reads `output.json`'s
  `results.stats` directly and fails the job on any `errors` or on a pass rate below
  `promptfoo.yaml`'s `threshold` (90%), rather than trusting promptfoo's bare exit code.
  Verified against both a reproduced 20-error run (correctly fails) and a synthetic
  18/2/0 (90% exactly at threshold) run (correctly passes).
- `hooks/post_gen_project.py`'s initial-commit fix (below) had its own bug: it ran
  `uv sync` (which writes `uv.lock`) *after* `git add -A` + the initial commit, so every
  freshly generated project left `uv.lock` untracked — despite `.gitignore` explicitly
  saying `# uv.lock is committed — do not add it here`. Confirmed via a real CI run:
  `astral-sh/setup-uv`'s cache step failed immediately with `No file matched to
  [**/uv.lock]` since the pushed repo never had it. Reordered so `uv sync` runs before
  `git add -A`/the commit; verified with a fresh generation that `uv.lock` (3717 lines) is
  now part of the initial commit and the tree is clean afterward.
- `hooks/post_gen_project.py` ran `git init` and `git add -A` but never committed —
  every generated project started with all files staged but zero commits, so
  `git log`/`gh repo create --push`/anything assuming an initial commit existed would
  fail immediately. Now commits (`chore: initial commit from agent-deployment-template`)
  right after staging, before pre-commit hooks are installed, so the initial commit isn't
  blocked by autofixing hooks (ruff/markdownlint) rewriting files mid-commit.
- Generated `README.md`/`CLAUDE.md` documented `GOOGLE_CLOUD_LOCATION`'s default as
  `us-central1`; the actual default in `deployment/config.py` and `setup_gcp.sh` has
  always been `europe-west1`. Docs now match the code.

### Added

- **Conventional-commit enforcement on PR titles in generated projects** (`lint-pr.yml`).
  The workflow previously existed only in the template repo and did not propagate, so
  generated projects had no server-side enforcement at all — only the local `commit-msg`
  hook. That gap mattered more than it looks: commitizen validates *commit messages on the
  contributor's branch*, but a squash merge discards those and uses the **PR title** as the
  subject of the commit that lands on `main` — the one `cz bump` reads to build
  `CHANGELOG.md`. The local hook is also bypassable with `--no-verify` or by committing
  through the GitHub web UI, so the string that reaches permanent history was the only one
  nothing checked. Its accepted types are deliberately the exact set
  `cz_conventional_commits` accepts (`build`, `bump`, `chore`, `ci`, `docs`, `feat`, `fix`,
  `perf`, `refactor`, `revert`, `style`, `test`), so a message the hook accepts is always a
  valid PR title. Documented in the generated `CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md`,
  whose CI/CD tables and commit-convention sections previously described the hook as the
  only enforcement.
- **Coverage now measures `deployment/`, not just `agent/`.** `pyproject.toml` scoped
  `--cov=agent`, so the reported 96% said nothing about the deployment path — and
  `deploy.py`, which pickles the agent and ships it to Agent Engine, had **zero tests
  anywhere**: not in generated projects, not in this template repo. It is the
  highest-blast-radius file in the template and was entirely unguarded. Scope is now
  `--cov=agent --cov=deployment`, with a `[tool.coverage.report] exclude_also` for the
  `if __name__ == "__main__":` argparse blocks in `deploy.py`/`health_check.py`, which no
  import-based test can reach. Widening the scope alone would have measured 74% and broken
  the 75% gate for every generated project; with the new tests below it measures **97.76%**
  (223 statements, 5 missed — all pre-existing, in `agent/observability.py`).
- Unit tests for the deploy path (`tests/unit/test_deploy.py`, 12 cases) taking
  `deployment/deploy.py` from 0% to 100%. Every cloud import in `deploy()` is function-local,
  so patching `vertexai.init`, `vertexai.agent_engines.get/create` and `run_smoke_test` at
  their source keeps the tests fully offline — nothing is pickled, uploaded or billed. Pins
  the behaviour that breaks silently: create-vs-update selection, `extra_packages` shipping
  both `agent` and `prompts` (the pickled agent references `agent.tools.*` by module path),
  `display_name` being sent on create but not on update, `.agent_engine_resource` being
  written for CI to read, and — most importantly — a failed smoke test exiting `1` rather
  than being logged and ignored. Also documents that `--env dev|prod` is informational only:
  it retargets nothing, since project/location/bucket all come from the environment.
- Unit tests for `check_resource` (`tests/unit/test_health_check.py`, 5 new cases) taking
  `deployment/scripts/health_check.py` from 50% to 100%. Covers the early return when
  `AGENT_ENGINE_RESOURCE_NAME` is unset — verifying `vertexai.init` is never called, so a
  health check can never accidentally become a deploy.
- Unit tests for `deployment/config.py` (`tests/unit/test_config.py`, 16 cases). Neither
  `resolve_model` nor `DeploymentConfig.from_env` had any test coverage, and because
  `pyproject.toml` scoped coverage to `--cov=agent`, the reported 96% never included
  `deployment/` at all (since widened — see above). The cookiecutter `model_provider`
  answer does not gate
  `resolve_model`'s branches — they are selected at runtime from `MODEL_PROVIDER` — so
  generating a project per provider could never have exercised them; tests are the only
  thing that can. Covers all four providers, the unknown-provider `ValueError`, the
  `litellm`-without-`LITELLM_MODEL` `KeyError`, and `from_env`'s `europe-west1` default
  (locking the code to what `README.md`/`CLAUDE.md` document) and empty-string
  `AGENT_ENGINE_RESOURCE_NAME` handling. `LiteLlm(...)` construction needs no API key and
  makes no network call, so every case is offline and deterministic.
- `validate-template.yml` now generates four cookiecutter variants instead of only the
  defaults — default, `python_version=3.12`, `open_source_license=Apache-2.0`, and
  `open_source_license=Proprietary` — and, for each, additionally runs `ruff format
  --check .` and the generated project's full `pre-commit` hook set. `make validate` gains
  the same format check. Every generated-project fix in this release was a defect that
  only the defaults-only validation had allowed through.
- Rollback support for Agent Engine deployments: `deploy.yml` accepts an optional `ref`
  `workflow_dispatch` input (defaults to the triggering ref), and generated projects get a
  `make rollback REF=<tag> [ENV=prod|dev]` target that redeploys a previous git ref against the
  existing Agent Engine resource. Documented in the generated project's `CLAUDE.md`.
- Standalone post-deployment health check: the smoke test previously inlined in `deploy.py` is
  now `deployment/scripts/health_check.py`, runnable against an existing Agent Engine resource
  without a fresh deploy. Exposed as `make health-check` and wired into `deploy.yml` as its own
  step after deploy (clear 0/1 exit codes for CI gating).
- Documented dev/prod environment separation: a "Required GitHub Environments" table in the
  generated `CLAUDE.md` spells out which secrets/variables belong to the `dev` and `prod`
  GitHub Environments (vs. the one repository-level secret used only by `eval.yml`).
  `setup_gcp.sh` now takes a `dev`/`prod` argument (`make setup-gcp ENV=dev`) and prints
  instructions scoped to that environment instead of generic repository secrets.
- Core observability library: `agent/observability.py` adds structured JSON logging
  (`log_event`), an `@instrument` decorator that logs name/duration/outcome for tool calls
  (applied to both example tools), PII redaction (email/SSN/credit-card patterns), and
  `log_model_usage()` for token-count logging where the event stream is iterated directly
  (the promptfoo eval provider). Documented in the generated project's `CLAUDE.md`.
- Cloud Logging integration: `log_event` now emits `severity` and `agent_name` fields —
  `severity` is a Cloud Logging reserved field (promoted out of `jsonPayload` into the LogEntry,
  filterable as `severity=ERROR`), and `agent_name` matches the filter `read_logs.sh` already
  used. Added Cloud Logging query examples to the generated `README.md`, a log-field reference
  table to `CLAUDE.md`, and 2 integration tests validating the JSON shape through the full
  mocked Runner pipeline.
- Cloud Monitoring dashboard and alert policies: `deployment/monitoring/` adds a dashboard
  (request count by response code, p50/p95/p99 latency, CPU/memory allocation) and two alert
  policies (5xx rate > 5%, p95 latency > 3000ms) against Agent Engine's built-in
  `reasoning_engine/*` metrics, applied via plain `gcloud` — this template uses no Terraform, so
  `setup_monitoring.sh` (new `make setup-monitoring` target) creates/updates them idempotently,
  with optional email/Slack notification channels. Rate-limit/quota alerting isn't included: no
  per-agent quota metric exists to threshold on; that's documented as a manual Cloud Console step.

## [1.1.0] - 2026-07-20

First cruft-aware release: generated projects can now track and pull in template updates
via `cruft check`/`cruft update` instead of only being generated once and left to drift.

### Fixed

- `hooks/post_gen_project.py` no longer crashes under `cruft create`/`cruft update`: those
  commands only inject `_template`/`_commit` into the cookiecutter context (not
  `_repo_dir`/`_checkout`, which plain `cookiecutter` provides), and the strict Jinja lookup
  raised `UndefinedError` and aborted generation. All private context lookups now use a
  Jinja `default` so both flows work.

### Added

- Template repo: `cruft` dev dependency for template maintainers to test `cruft create`/`cruft update`
- Generated repo: `.cruft.json` auto-generated by `hooks/post_gen_project.py`, pinning the exact
  template commit used so `cruft check`/`cruft update` can track drift later
- README: documented `cruft create` as the canonical project generation method, with a
  "keeping in sync" section covering `cruft check`/`cruft update`
- Generated repo: `cruft-check.yml` workflow — non-blocking drift check that warns when the
  project has fallen behind the template (`cruft check` on push/PR/weekly schedule)
- Template versioning discipline documented in `CLAUDE.md`, so releases are tagged and
  generated projects have a controlled `cruft update --checkout <tag>` upgrade path

## [1.0.0] - 2026-07-20

Initial template baseline, tagged retroactively as the `1.0.0` reference point that
`1.1.0` and later releases version against. No `v1.0.0` git tag exists — only `v1.1.0`
onward are tagged (see [Template Versioning](CLAUDE.md#template-versioning)).

### Added

- Initial cookiecutter template with full ADK agent scaffold
- `cookiecutter.json` with project metadata and model provider selection
- `hooks/pre_gen_project.py` — input validation before generation
- `hooks/post_gen_project.py` — git init, uv sync, pre-commit install after generation
- Generated repo: Google ADK `root_agent` with `get_current_datetime` and `web_search` tools
- Generated repo: `prompts/` directory with YAML registry for prompt composition
- Generated repo: `deployment/` with Agent Engine deploy script and GCP bootstrap scripts
- Generated repo: `tests/unit/` with tool and model tests
- Generated repo: `tests/evals/` with promptfoo red-team configuration
- Generated repo: GitHub Actions CI, security, eval, and deploy workflows
- Generated repo: `CLAUDE.md` with full developer and AI assistant instructions
- Generated repo: `.claude/commands/` with `/deploy`, `/eval`, `/logs` slash commands
- Template repo: `ci.yml`, `validate-template.yml`, `lint-pr.yml` workflows
- Template repo: `CLAUDE.md` with template contribution instructions
