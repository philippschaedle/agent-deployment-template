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
make setup-gcp   # creates SA, enables APIs, generates key for CI
```

## Project layout

```text
agent/
  __init__.py          load_prompt() — reads prompts/prompts.yaml and concatenates .md files
  agent.py             root_agent definition (ADK syntax; this is the entrypoint)
  tools/
    __init__.py        re-exports all tools
    example_tools.py   get_current_datetime, web_search
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
    read_logs.sh       stream Cloud Logging
    read_traces.sh     open Cloud Trace in browser
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
| `make eval` | promptfoo red-team evaluation |
| `make lint` | ruff lint check |
| `make format` | ruff format |
| `make typecheck` | pyright |
| `make pre-commit` | All pre-commit hooks |
| `make deploy-dev` | Deploy to Agent Engine (dev) |
| `make deploy-prod` | Deploy to Agent Engine (prod) |
| `make logs` | Stream Cloud Logging |
| `make traces` | Open Cloud Trace in browser |
| `make setup-gcp` | One-time GCP bootstrap |

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
| `GOOGLE_CLOUD_LOCATION` | Deploy only | `us-central1` | Vertex AI region |
| `GCS_STAGING_BUCKET` | Deploy only | — | GCS bucket for Agent Engine artefacts |
| `AGENT_ENGINE_RESOURCE_NAME` | No | — | Existing resource to update (omit = create new) |
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

## Conventional commits (enforced by commitizen hook)

Format: `type(scope): description`

```text
feat(agent): add calendar lookup tool
fix(prompts): correct safety guidelines for PII handling
chore(deps): bump google-adk to 1.1.0
docs(readme): update deployment instructions
test(evals): add promptfoo test for jailbreak via roleplay
refactor(deployment): simplify config dataclass
```

The commit-msg hook will reject non-conforming messages.

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

## CI/CD overview

| Workflow | Trigger | What it checks |
|---|---|---|
| `ci.yml` | push + PR | lint, format, typecheck, unit tests |
| `security.yml` | push to main + weekly | CodeQL, pip-audit CVEs, secret scan |
| `eval.yml` | PR to main | promptfoo red-team (90% pass threshold) |
| `deploy.yml` | push to main | deploys to Agent Engine prod |
| `cruft-check.yml` | push + PR + weekly | non-blocking: warns if `cruft update` is available from the template |

Required GitHub Secrets: `GCP_SA_KEY`, `GOOGLE_CLOUD_PROJECT`, `GCS_STAGING_BUCKET`, `GOOGLE_API_KEY`  # pragma: allowlist secret
Required GitHub Variables: `GOOGLE_CLOUD_LOCATION`, `MODEL_PROVIDER`, `AGENT_ENGINE_RESOURCE_NAME` (after first deploy)
