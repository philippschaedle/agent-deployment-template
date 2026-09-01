# Changelog

All notable changes to this cookiecutter template are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — see
[Template Versioning](CLAUDE.md#template-versioning) in `CLAUDE.md` for what bumps count as
MAJOR/MINOR/PATCH and how releases are tagged.

## [Unreleased]

### Fixed

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
