import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_SHA256_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}$")


def validate_image_digest(image_digest: str) -> str:
    """Validate a container image digest ends in a well-formed sha256 digest.

    Accepts either a bare digest (`sha256:<64 hex chars>`) or a full,
    digest-pinned image reference (`registry/repo@sha256:<64 hex chars>`,
    e.g. build.yml's `image_ref` output). Raises ValueError otherwise.
    """
    if not _SHA256_DIGEST_RE.search(image_digest):
        raise ValueError(
            f"Invalid image digest {image_digest!r}: expected 'sha256:<64 hex "
            "chars>' or '<image>@sha256:<64 hex chars>' (see build.yml's "
            "image_ref output)."
        )
    return image_digest


def _project_name() -> str:
    """Read the project name from pyproject.toml so derived names stay in sync."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        return tomllib.load(f)["project"]["name"]


def resolve_model():
    """Return the ADK-compatible model handle based on MODEL_PROVIDER env var.

    Supported values for MODEL_PROVIDER:
      google    (default) — Gemini 2.5 Pro via native ADK
      anthropic           — Claude via LiteLLM
      openai              — GPT-4o via LiteLLM
      litellm             — any model; set LITELLM_MODEL to the full model string
    """
    provider = os.getenv("MODEL_PROVIDER", "google").lower()

    if provider == "google":
        return "gemini-2.5-pro"

    from google.adk.models.lite_llm import LiteLlm  # noqa: PLC0415

    match provider:
        case "anthropic":
            return LiteLlm(model="anthropic/claude-opus-4-8")
        case "openai":
            return LiteLlm(model="openai/gpt-4o")
        case "litellm":
            model = os.environ["LITELLM_MODEL"]
            return LiteLlm(model=model)
        case _:
            raise ValueError(
                f"Unknown MODEL_PROVIDER: {provider!r}. "
                "Valid options: google, anthropic, openai, litellm"
            )


@dataclass
class DeploymentConfig:
    project: str
    location: str
    staging_bucket: str
    resource_name: str | None
    agent_display_name: str
    gcs_dir_name: str

    @classmethod
    def from_env(cls) -> "DeploymentConfig":
        return cls(
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "europe-west1"),
            staging_bucket=os.environ["GCS_STAGING_BUCKET"],
            resource_name=os.getenv("AGENT_ENGINE_RESOURCE_NAME") or None,
            agent_display_name="{{cookiecutter.project_name}}",
            # Staging subfolder within the bucket; project-named so artifacts
            # land at <bucket>/data-trace-agent/ instead of the generic default.
            gcs_dir_name=_project_name(),
        )
