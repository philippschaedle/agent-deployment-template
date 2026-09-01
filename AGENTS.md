# AGENTS.md — ADK Agent Deployment Template

This file is read automatically by AI coding assistants (Claude Code, Cursor, GitHub Copilot, Gemini Code Assist, etc.). It contains everything needed to work on this repository.

## What this repository is

A **cookiecutter template** that generates production-ready [Google ADK](https://google.github.io/adk-docs/) agent repositories. Running `cookiecutter .` produces a new repo with a working agent, CI/CD, deployment scripts, and prompt security evaluation already configured.

**Critical**: all files inside `{{cookiecutter.project_slug}}/` are Jinja2 templates rendered by cookiecutter. They are not runnable code. Do not run them directly — test changes with `make validate` instead.

## Setup

```bash
# Prerequisites: Python 3.11+, uv, cookiecutter
make install    # install dev dependencies (ruff, pyright, commitizen) + git hooks
make validate   # generate a test project and verify it compiles + tests pass
```

## Make targets

| Target | Description |
| --- | --- |
| `make install` | Install dev dependencies with uv, then install git hooks |
| `make lint` | Ruff lint check on hooks/ |
| `make format` | Ruff format on hooks/ |
| `make typecheck` | Pyright on hooks/ |
| `make validate` | Generate test project → run its lint + unit tests |
| `make pre-commit` | Run all pre-commit hooks on all files |

## Repository structure

```text
cookiecutter.json               variables collected at generation time
hooks/
  pre_gen_project.py            validates inputs before generation
  post_gen_project.py           git init, uv sync, pre-commit install after generation
{{cookiecutter.project_slug}}/  TEMPLATE — becomes the generated agent repo
  agent/                        ADK root_agent + tools + prompt loader
  prompts/                      prompt .md files + YAML registry
  deployment/                   Agent Engine deploy script + GCP scripts
  tests/                        unit tests + promptfoo evals
  .github/workflows/            CI (lint/test), security, eval, deploy
  CLAUDE.md                     Claude Code instructions for the generated repo
  AGENTS.md                     AI assistant instructions for the generated repo
.github/workflows/
  ci.yml                        lint hooks/, validate cookiecutter.json
  validate-template.yml         generate project + run its tests
  lint-pr.yml                   enforce conventional commit PR titles
CLAUDE.md                       Claude Code instructions for this template repo
AGENTS.md                       this file
```

## Working on this template

### Adding a cookiecutter variable

1. Add to `cookiecutter.json`
2. Reference in template files as `{{cookiecutter.your_variable}}`
3. Update the README variables table
4. Run `make validate`

### Testing changes

Always run `make validate` before committing — it generates a real project and verifies it passes lint and unit tests.

### Jinja2 / GitHub Actions conflict

GitHub Actions uses `${{ }}` syntax which conflicts with Jinja2. Any `${{ }}` expression inside `{{cookiecutter.project_slug}}/.github/workflows/` must be wrapped with `{% raw %}...{% endraw %}`.

## Code conventions

- **Conventional commits** enforced by commitizen: `feat(scope): description`
- **Pre-commit hooks**: ruff (lint + format), pyright, detect-secrets, markdownlint
- Run `make pre-commit` before every commit; never use `--no-verify`
- Update `CHANGELOG.md` under `[Unreleased]` for every user-facing change
- No `print()` in Python package code — use `logging`

## GitHub Actions (this repo)

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `ci.yml` | push + PR | Lints hooks/, validates cookiecutter.json |
| `validate-template.yml` | push + PR | Generates project, runs its lint + unit tests |
| `lint-pr.yml` | PR open/edit | Enforces conventional commit PR title |
