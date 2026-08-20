#!/usr/bin/env python3
"""Post-deployment health check for a Vertex AI Agent Engine resource.

Runs the smoke test (send a message, require at least one event back) against
an already-deployed resource. Used both as a standalone CLI — to check a
resource without doing a fresh deploy, e.g. right after a rollback — and as a
shared helper called from deployment/deploy.py immediately after deploying.

Usage:
    uv run python deployment/scripts/health_check.py
    uv run python deployment/scripts/health_check.py --message "hello" --user-id healthcheck
"""
import argparse
import logging
import os
import sys

# Ensure the project root is on the path when run as a script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_smoke_test(remote_agent, message: str = "ping", user_id: str = "smoke-test") -> bool:
    """Send `message` to `remote_agent` and require at least one event back.

    `remote_agent` is whatever `agent_engines.create/update/get` returns — a
    deployed ADK agent exposes `stream_query` (a generator of event dicts),
    not `query`.
    """
    events = list(
        remote_agent.stream_query(  # type: ignore[attr-defined]
            message=message, user_id=user_id
        )
    )
    if not events:
        logger.error("Health check failed: no events returned.")
        return False

    logger.info("Health check passed: %d event(s) returned.", len(events))
    return True


def check_resource(message: str, user_id: str) -> bool:
    """Fetch the resource named by AGENT_ENGINE_RESOURCE_NAME and smoke-test it."""
    import vertexai
    from vertexai import agent_engines

    from deployment.config import DeploymentConfig

    config = DeploymentConfig.from_env()

    if not config.resource_name:
        logger.error(
            "AGENT_ENGINE_RESOURCE_NAME is not set — health check needs an existing "
            "deployed resource to query, not a fresh deploy."
        )
        return False

    logger.info("Health-checking: %s", config.resource_name)

    vertexai.init(project=config.project, location=config.location)
    remote_agent = agent_engines.get(config.resource_name)

    return run_smoke_test(remote_agent, message=message, user_id=user_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run a standalone health check against a deployed Agent Engine resource"
    )
    parser.add_argument(
        "--message", default="ping", help="Message to send for the smoke test (default: ping)"
    )
    parser.add_argument(
        "--user-id",
        default="health-check",
        help="User ID to attribute the smoke-test query to (default: health-check)",
    )
    args = parser.parse_args()
    sys.exit(0 if check_resource(args.message, args.user_id) else 1)
