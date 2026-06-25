"""Shared fixtures for integration tests.

Patches Runner.run_async to return pre-written events so agent pipeline tests
never make real LLM API calls.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


def _make_text_event(text: str) -> MagicMock:
    """Return a mock ADK Event that represents a final text response."""
    part = MagicMock()
    part.text = text
    content = MagicMock()
    content.parts = [part]
    event = MagicMock()
    event.is_final_response.return_value = True
    event.content = content
    return event


def _make_intermediate_event() -> MagicMock:
    """Return a mock ADK Event that represents a non-final step (e.g. tool in progress)."""
    event = MagicMock()
    event.is_final_response.return_value = False
    event.content = None
    return event


@pytest.fixture
def make_text_event():
    """Factory: build a final-response event carrying the given text."""
    return _make_text_event


@pytest.fixture
def make_intermediate_event():
    """Factory: build a non-final in-progress event."""
    return _make_intermediate_event


@pytest.fixture
def patch_runner(monkeypatch):
    """Replace Runner.run_async with a controlled async generator.

    Call the returned function at the start of each test, passing the list of
    events the fake runner should yield::

        async def test_something(patch_runner, make_text_event):
            patch_runner([make_text_event("Hello!")])
            result = await _run_agent("hi")
            assert result == "Hello!"

    The patch is automatically undone after each test via monkeypatch cleanup.
    """

    def _apply(events: list[Any]) -> None:
        async def _fake_run_async(self, **kwargs):  # noqa: ARG001
            for event in events:
                yield event

        monkeypatch.setattr("google.adk.runners.Runner.run_async", _fake_run_async)

    return _apply
