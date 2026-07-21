#!/usr/bin/env python3
"""Deploy the agent to Vertex AI Agent Engine.

Usage:
    uv run python deployment/deploy.py --env dev
    uv run python deployment/deploy.py --env prod
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure the project root is on the path when run as a script
# (python deployment/deploy.py puts deployment/ on sys.path, not the root).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def deploy(env: str, image_digest: str | None = None) -> None:
    """Deploy the agent to Vertex AI Agent Engine.

    Deploys are source-based: Agent Engine pickles `root_agent` and its
    dependencies directly, it does not run a container image. Pass
    `image_digest` — the digest-pinned image ref from build.yml's `image_ref`
    output (e.g. `registry/repo@sha256:...`) — to record which container
    image was built for this commit as the resource's description, purely
    for traceability. It is validated but never deployed.
    """
    import vertexai
    from vertexai import agent_engines

    from agent.agent import root_agent
    from deployment.config import DeploymentConfig, validate_image_digest

    config = DeploymentConfig.from_env()

    if image_digest is not None:
        image_digest = validate_image_digest(image_digest)

    logger.info("Deploying [%s] to Vertex AI Agent Engine", env)
    logger.info("  Project:  %s", config.project)
    logger.info("  Location: %s", config.location)
    logger.info("  Bucket:   %s", config.staging_bucket)
    if image_digest:
        logger.info("  Image:    %s", image_digest)

    vertexai.init(
        project=config.project,
        location=config.location,
        staging_bucket=config.staging_bucket,
    )

    requirements = [
        "google-adk>=1.0.0",
        "google-cloud-aiplatform[agent_engines]>=1.90.0",
        "litellm>=1.50.0",
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
    ]

    # Local source that must be importable on the remote container. The pickled
    # agent references agent.tools.* by module path, so the package has to ship
    # alongside it (the prompts dir travels too for any runtime reads).
    extra_packages = ["agent", "prompts"]

    # Purely informational — Agent Engine does not run this image, but recording
    # it on the resource lets you trace a deploy back to the commit/image it
    # came from without cross-referencing CI run history.
    description = f"Built from image {image_digest}" if image_digest else None

    if config.resource_name:
        logger.info("  Updating: %s", config.resource_name)
        existing = agent_engines.get(config.resource_name)
        update_kwargs = dict(
            agent_engine=root_agent,
            requirements=requirements,
            extra_packages=extra_packages,
            gcs_dir_name=config.gcs_dir_name,
        )
        if description:
            update_kwargs["description"] = description
        remote_agent = existing.update(**update_kwargs)
    else:
        logger.info("  Creating new Agent Engine resource...")
        create_kwargs = dict(
            agent_engine=root_agent,
            requirements=requirements,
            display_name=config.agent_display_name,
            gcs_dir_name=config.gcs_dir_name,
            extra_packages=extra_packages,
        )
        if description:
            create_kwargs["description"] = description
        remote_agent = agent_engines.create(**create_kwargs)

    resource_name = remote_agent.resource_name
    logger.info("Deployed: %s", resource_name)

    Path(".agent_engine_resource").write_text(resource_name + "\n")

    logger.info("Running smoke test...")
        # A deployed ADK agent exposes stream_query (a generator of event dicts),
    # not query. Drain it and require at least one event back.
    events = list(
        remote_agent.stream_query(  # type: ignore[attr-defined]
            message="ping", user_id="smoke-test"
        )
    )
    if not events:
        logger.error("Smoke test returned no events.")
        sys.exit(1)
    logger.info("Smoke test passed.")

    # Emit for CI capture
    logger.info("AGENT_ENGINE_RESOURCE_NAME=%s", resource_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy agent to Vertex AI Agent Engine")
    parser.add_argument(
        "--env",
        choices=["dev", "prod"],
        default="prod",
        help="Target environment (default: prod)",
    )
    parser.add_argument(
        "--image-digest",
        default=os.getenv("IMAGE_DIGEST"),
        help=(
            "Digest-pinned image ref from build.yml's image_ref output "
            "(default: $IMAGE_DIGEST env var). Recorded as metadata only — "
            "this deploy is source-based and does not run the image."
        ),
    )
    args = parser.parse_args()
    deploy(args.env, args.image_digest)
