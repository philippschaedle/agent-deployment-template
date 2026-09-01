"""Unit tests for the Agent Engine deploy path — no network, no GCP credentials required.

`deploy()` imports `vertexai`, `vertexai.agent_engines`, `agent.agent.root_agent` and
`run_smoke_test` inside the function body, so patching each at its source module keeps
every test here offline: nothing is pickled, uploaded, or billed.

This is the highest-blast-radius code in the template — it ships the agent to production —
so the tests below pin the behaviour that is easy to break silently: which of
create/update is chosen, what gets handed to each, and that a failed smoke test actually
fails the process instead of being logged and ignored.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from deployment.deploy import deploy

RESOURCE = "projects/p/locations/l/reasoningEngines/42"


@pytest.fixture
def deploy_env(monkeypatch, tmp_path):
    """Deploy-time environment, with a CWD that absorbs `.agent_engine_resource`."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project-123")
    monkeypatch.setenv("GCS_STAGING_BUCKET", "gs://test-staging-bucket")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west1")
    monkeypatch.delenv("AGENT_ENGINE_RESOURCE_NAME", raising=False)
    # deploy() writes .agent_engine_resource relative to the CWD, not the project root.
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def deps():
    """Patched Vertex AI surface. `create` and `update` both yield the same remote agent."""
    remote_agent = Mock()
    remote_agent.resource_name = RESOURCE

    with (
        patch("vertexai.init") as init,
        patch("vertexai.agent_engines.get") as get,
        patch("vertexai.agent_engines.create", return_value=remote_agent) as create,
        patch(
            "deployment.scripts.health_check.run_smoke_test", return_value=True
        ) as smoke,
    ):
        get.return_value.update.return_value = remote_agent
        yield SimpleNamespace(
            init=init, get=get, create=create, smoke=smoke, remote_agent=remote_agent
        )


def test_deploy_creates_new_resource_when_none_configured(deploy_env, deps):
    deploy("dev")

    deps.create.assert_called_once()
    deps.get.assert_not_called()


def test_deploy_updates_existing_resource_when_configured(
    deploy_env, deps, monkeypatch
):
    monkeypatch.setenv("AGENT_ENGINE_RESOURCE_NAME", RESOURCE)

    deploy("prod")

    deps.get.assert_called_once_with(RESOURCE)
    deps.get.return_value.update.assert_called_once()
    deps.create.assert_not_called()


def test_deploy_initialises_vertexai_with_staging_bucket(deploy_env, deps):
    deploy("dev")

    deps.init.assert_called_once_with(
        project="test-project-123",
        location="europe-west1",
        staging_bucket="gs://test-staging-bucket",
    )


def test_deploy_ships_agent_and_prompts_as_extra_packages(deploy_env, deps):
    """The pickled agent references agent.tools.* by module path, so both must travel."""
    deploy("dev")

    assert deps.create.call_args.kwargs["extra_packages"] == ["agent", "prompts"]


def test_deploy_sets_display_name_when_creating(deploy_env, deps):
    deploy("dev")

    assert deps.create.call_args.kwargs["display_name"]


def test_deploy_does_not_send_display_name_when_updating(deploy_env, deps, monkeypatch):
    """Updating keeps the resource's existing display name — renaming is not a deploy concern."""
    monkeypatch.setenv("AGENT_ENGINE_RESOURCE_NAME", RESOURCE)

    deploy("prod")

    assert "display_name" not in deps.get.return_value.update.call_args.kwargs


def test_deploy_writes_resource_name_file(deploy_env, deps):
    """deploy.yml reads this file to learn the resource name after either create or update."""
    deploy("dev")

    assert (deploy_env / ".agent_engine_resource").read_text() == RESOURCE + "\n"


def test_deploy_runs_smoke_test_against_the_deployed_agent(deploy_env, deps):
    deploy("dev")

    deps.smoke.assert_called_once_with(deps.remote_agent)


def test_deploy_exits_nonzero_when_smoke_test_fails(deploy_env, deps):
    """A deployed-but-broken agent must fail the job, not pass quietly."""
    deps.smoke.return_value = False

    with pytest.raises(SystemExit) as excinfo:
        deploy("dev")

    assert excinfo.value.code == 1


def test_deploy_writes_resource_file_before_smoke_test_fails(deploy_env, deps):
    """The resource exists even when the smoke test fails — CI still needs its name."""
    deps.smoke.return_value = False

    with pytest.raises(SystemExit):
        deploy("dev")

    assert (deploy_env / ".agent_engine_resource").read_text() == RESOURCE + "\n"


def test_deploy_env_argument_is_informational_only(deploy_env, deps):
    """`--env dev` does not retarget anything: project/location/bucket come from the
    environment. Deploying to dev vs prod is a matter of which .env or GitHub Environment
    is in scope, not of this argument."""
    deploy("dev")
    dev_kwargs = deps.init.call_args.kwargs

    deps.init.reset_mock()
    deploy("prod")

    assert deps.init.call_args.kwargs == dev_kwargs
