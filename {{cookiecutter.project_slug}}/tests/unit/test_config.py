"""Unit tests for deployment config — no network, no GCP credentials required.

`resolve_model`'s non-Google branches are only reachable at runtime via MODEL_PROVIDER;
the cookiecutter `model_provider` answer does not gate them at generation time. Tests are
the only thing that exercises them, so they are covered here rather than by generating a
project per provider. `LiteLlm(...)` construction makes no network call and needs no API
key, so every branch below is deterministic and offline.
"""

import pytest
from google.adk.models.lite_llm import LiteLlm

from deployment.config import DeploymentConfig, resolve_model


def test_resolve_model_defaults_to_google(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)

    assert resolve_model() == "gemini-2.5-pro"


def test_resolve_model_returns_plain_string_for_google(monkeypatch):
    """The google branch returns a bare model id, not a LiteLlm wrapper."""
    monkeypatch.setenv("MODEL_PROVIDER", "google")

    assert resolve_model() == "gemini-2.5-pro"


def test_resolve_model_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "AnThRoPiC")

    model = resolve_model()

    assert isinstance(model, LiteLlm)
    assert model.model == "anthropic/claude-opus-4-8"


def test_resolve_model_anthropic_uses_litellm(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")

    model = resolve_model()

    assert isinstance(model, LiteLlm)
    assert model.model == "anthropic/claude-opus-4-8"


def test_resolve_model_openai_uses_litellm(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")

    model = resolve_model()

    assert isinstance(model, LiteLlm)
    assert model.model == "openai/gpt-4o"


def test_resolve_model_litellm_reads_litellm_model_env(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "litellm")
    monkeypatch.setenv("LITELLM_MODEL", "mistral/mistral-large-latest")

    model = resolve_model()

    assert isinstance(model, LiteLlm)
    assert model.model == "mistral/mistral-large-latest"


def test_resolve_model_litellm_without_model_env_raises(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "litellm")
    monkeypatch.delenv("LITELLM_MODEL", raising=False)

    with pytest.raises(KeyError):
        resolve_model()


def test_resolve_model_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "bedrock")

    with pytest.raises(ValueError, match="Unknown MODEL_PROVIDER"):
        resolve_model()


@pytest.fixture
def required_deploy_env(monkeypatch):
    """The two variables DeploymentConfig.from_env has no default for."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project-123")
    monkeypatch.setenv("GCS_STAGING_BUCKET", "gs://test-staging-bucket")


def test_from_env_defaults_location_to_europe_west1(monkeypatch, required_deploy_env):
    """Documented default in README.md and CLAUDE.md — keep the docs and code in step."""
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)

    assert DeploymentConfig.from_env().location == "europe-west1"


def test_from_env_honours_explicit_location(monkeypatch, required_deploy_env):
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    assert DeploymentConfig.from_env().location == "us-central1"


def test_from_env_reads_project_and_bucket(monkeypatch, required_deploy_env):
    config = DeploymentConfig.from_env()

    assert config.project == "test-project-123"
    assert config.staging_bucket == "gs://test-staging-bucket"


def test_from_env_treats_empty_resource_name_as_none(monkeypatch, required_deploy_env):
    """An unset GitHub Actions variable arrives as "", which must mean "create new"."""
    monkeypatch.setenv("AGENT_ENGINE_RESOURCE_NAME", "")

    assert DeploymentConfig.from_env().resource_name is None


def test_from_env_keeps_resource_name_when_set(monkeypatch, required_deploy_env):
    monkeypatch.setenv(
        "AGENT_ENGINE_RESOURCE_NAME", "projects/p/locations/l/reasoningEngines/1"
    )

    assert (
        DeploymentConfig.from_env().resource_name
        == "projects/p/locations/l/reasoningEngines/1"
    )


def test_from_env_requires_project(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setenv("GCS_STAGING_BUCKET", "gs://test-staging-bucket")

    with pytest.raises(KeyError):
        DeploymentConfig.from_env()


def test_from_env_derives_gcs_dir_name_from_pyproject(required_deploy_env):
    """gcs_dir_name comes from pyproject.toml's project name, not the display name."""
    # Bound to a name rather than inlined: a cookiecutter substitution changes the line's
    # length, so an inlined literal formats differently before and after rendering and
    # `ruff format --check` then fails in the generated project.
    expected = "{{cookiecutter.project_slug}}"

    assert DeploymentConfig.from_env().gcs_dir_name == expected


def test_from_env_uses_project_name_as_display_name(required_deploy_env):
    expected = "{{cookiecutter.project_name}}"

    assert DeploymentConfig.from_env().agent_display_name == expected
