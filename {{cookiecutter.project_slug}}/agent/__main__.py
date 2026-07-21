"""Container entrypoint: `python -m agent` serves this agent via `adk api_server`."""

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m agent",
        description=(
            "Serve {{ cookiecutter.project_name }} via `adk api_server`. "
            "Binds to $PORT by default, matching Cloud Run's convention."
        ),
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument(
        "--port",
        default=os.environ.get("PORT", "8080"),
        help="Bind port (default: $PORT env var, else 8080)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    os.execvp(
        "adk",
        ["adk", "api_server", "--host", args.host, "--port", str(args.port), str(project_root)],
    )


if __name__ == "__main__":
    main()
