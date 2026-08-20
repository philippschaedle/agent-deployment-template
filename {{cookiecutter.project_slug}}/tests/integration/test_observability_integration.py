"""Integration tests validating structured log output through the full eval pipeline.

Exercises tests/evals/provider.py's _run_agent -- the same choke point used by
tests/integration/test_agent_runner.py -- but asserts on the JSON log lines
agent/observability.py emits rather than on the returned text.
"""

import json


async def test_pipeline_logs_model_usage_as_structured_json(
    monkeypatch, patch_runner, make_text_event_with_usage
):
    messages = []
    monkeypatch.setattr(
        "agent.observability.logger.info", lambda m: messages.append(json.loads(m))
    )
    patch_runner(
        [make_text_event_with_usage("Done.", prompt_tokens=12, candidates_tokens=4)]
    )

    from tests.evals.provider import _run_agent

    result = await _run_agent("hello")

    assert result == "Done."
    usage_events = [m for m in messages if m["event"] == "model.usage"]
    assert usage_events == [
        {
            "severity": "INFO",
            "agent_name": "root_agent",
            "event": "model.usage",
            "prompt_tokens": 12,
            "candidates_tokens": 4,
            "total_tokens": 16,
        }
    ]


async def test_pipeline_logs_nothing_when_usage_metadata_absent(
    monkeypatch, patch_runner, make_text_event
):
    messages = []
    monkeypatch.setattr(
        "agent.observability.logger.info", lambda m: messages.append(json.loads(m))
    )
    patch_runner([make_text_event("Hi.")])

    from tests.evals.provider import _run_agent

    await _run_agent("hello")

    assert not [m for m in messages if m["event"] == "model.usage"]
