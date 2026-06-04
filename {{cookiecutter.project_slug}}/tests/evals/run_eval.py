#!/usr/bin/env python3
"""Local evaluation runner with human-readable output.

Usage:
    uv run python tests/evals/run_eval.py

This is a convenience wrapper around `make eval` (npx promptfoo).
Use it for quick local runs without needing Node.js promptfoo output parsing.
"""

import os
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).parent / "promptfoo.yaml"


def main() -> None:
    print("Running promptfoo evaluation...")
    print(f"Config: {CONFIG}\n")

    # Get the current environment to pass to promptfoo
    env = os.environ.copy()

    # Ensure promptfoo can access the current Python environment
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent)

    # Disable OpenTelemetry to avoid context errors in the ADK
    env["OTEL_SDK_DISABLED"] = "true"

    result = subprocess.run(
        ["npx", "--yes", "promptfoo@latest", "eval", "--config", str(CONFIG)],
        capture_output=False,
        env=env,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
