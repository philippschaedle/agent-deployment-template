import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(os.path.realpath(os.path.curdir))
LICENSE_CHOICE = "{{ cookiecutter.open_source_license }}"
PROJECT_SLUG = "{{ cookiecutter.project_slug }}"

# Cookiecutter injects these private keys into the context at generation time.
TEMPLATE_URL = "{{ cookiecutter._template }}"
TEMPLATE_REPO_DIR = "{{ cookiecutter._repo_dir }}"
TEMPLATE_CHECKOUT = "{{ cookiecutter._checkout }}"

CRUFT_CONTEXT = {
    "project_name": "{{ cookiecutter.project_name }}",
    "project_slug": "{{ cookiecutter.project_slug }}",
    "project_description": "{{ cookiecutter.project_description }}",
    "author_name": "{{ cookiecutter.author_name }}",
    "author_email": "{{ cookiecutter.author_email }}",
    "github_org": "{{ cookiecutter.github_org }}",
    "gcp_project_id": "{{ cookiecutter.gcp_project_id }}",
    "gcp_location": "{{ cookiecutter.gcp_location }}",
    "model_provider": "{{ cookiecutter.model_provider }}",
    "python_version": "{{ cookiecutter.python_version }}",
    "open_source_license": "{{ cookiecutter.open_source_license }}",
    "_template": TEMPLATE_URL,
}


def run(cmd: str, check: bool = True) -> int:
    result = subprocess.run(cmd, shell=True, cwd=PROJECT_DIR)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def remove_file(relative_path: str) -> None:
    target = PROJECT_DIR / relative_path
    if target.exists():
        target.unlink()


def uv_available() -> bool:
    return subprocess.run("which uv", shell=True, capture_output=True).returncode == 0


def get_template_commit() -> str:
    if not TEMPLATE_REPO_DIR:
        return ""
    result = subprocess.run(
        "git rev-parse HEAD",
        shell=True,
        cwd=TEMPLATE_REPO_DIR,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def write_cruft_json() -> None:
    cruft_config = {
        "template": TEMPLATE_URL,
        "commit": get_template_commit(),
        "checkout": TEMPLATE_CHECKOUT if TEMPLATE_CHECKOUT != "None" else None,
        "context": {"cookiecutter": CRUFT_CONTEXT},
        "directory": None,
    }
    cruft_json = PROJECT_DIR / ".cruft.json"
    cruft_json.write_text(json.dumps(cruft_config, indent=2) + "\n")


# Remove license file for proprietary projects
if LICENSE_CHOICE == "Proprietary":
    remove_file("LICENSE")

# Track the template commit so `cruft check`/`cruft update` work later,
# even for projects generated via plain `cookiecutter` rather than `cruft create`.
print("\n> Recording template version in .cruft.json...")
write_cruft_json()

# Initialise git
print("\n> Initialising git repository...")
run("git init")
run("git add -A")

# Install dependencies and pre-commit hooks
if uv_available():
    print("\n> Installing dependencies with uv...")
    run("uv sync")
    print("\n> Installing pre-commit hooks...")
    run("uv run pre-commit install")
    run("uv run pre-commit install --hook-type commit-msg")
else:
    print(
        "\nWARNING: uv not found. Install from https://docs.astral.sh/uv/ then run:\n"
        "  uv sync\n"
        "  uv run pre-commit install\n"
        "  uv run pre-commit install --hook-type commit-msg"
    )

print(
    f"""
{"=" * 60}
 Agent repository created: {PROJECT_SLUG}
{"=" * 60}

Next steps:
  1. cd {PROJECT_SLUG}
  2. cp .env.example .env
  3. Fill in API keys and GCP settings in .env
  4. make dev          # run the agent locally at http://localhost:8000
  5. make test         # run unit tests
  6. make setup-gcp    # one-time GCP bootstrap (when ready to deploy)
  7. make deploy-dev   # deploy to Agent Engine (dev)

See README.md and CLAUDE.md for full documentation.
"""
)
