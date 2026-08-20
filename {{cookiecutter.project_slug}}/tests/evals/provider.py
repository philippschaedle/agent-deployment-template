"""Promptfoo Python provider — runs root_agent inline, no HTTP server required.

Promptfoo calls call_api(prompt, options, context) for each test case.
"""

import asyncio
import os
import sys

# Ensure project root is on the path when called by promptfoo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv

load_dotenv()


async def _run_agent(prompt: str) -> str:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from agent.agent import root_agent
    from agent.observability import log_model_usage

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name="{{cookiecutter.project_slug}}",
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name="{{cookiecutter.project_slug}}",
        user_id="eval_user",
    )
    content = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )
    async for event in runner.run_async(
        user_id="eval_user",
        session_id=session.id,
        new_message=content,
    ):
        log_model_usage(event)
        if event.is_final_response() and event.content and event.content.parts:
            return event.content.parts[0].text or ""
    return ""


def call_api(prompt: str, options: dict, context: dict) -> dict:  # noqa: ARG001
    """Promptfoo provider entrypoint."""
    output = asyncio.run(_run_agent(prompt))
    return {"output": output}
