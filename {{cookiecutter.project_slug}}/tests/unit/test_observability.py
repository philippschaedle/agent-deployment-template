"""Unit tests for agent/observability.py — no network, no GCP credentials required."""

import json

import pytest

from agent.observability import instrument, log_event, log_model_usage, redact_pii


def test_redact_pii_masks_email():
    assert (
        redact_pii("contact me at jane@example.com") == "contact me at [REDACTED_EMAIL]"
    )


def test_redact_pii_masks_ssn():
    assert redact_pii("SSN: 123-45-6789") == "SSN: [REDACTED_SSN]"


def test_redact_pii_masks_credit_card():
    assert redact_pii("card 4111 1111 1111 1111") == "card [REDACTED_CARD]"


def test_redact_pii_recurses_into_dict_and_list():
    result = redact_pii({"emails": ["a@b.com", "no pii here"]})
    assert result == {"emails": ["[REDACTED_EMAIL]", "no pii here"]}


def test_redact_pii_passes_through_non_string():
    assert redact_pii(42) == 42
    assert redact_pii(None) is None


def test_log_event_emits_json_with_event_type(monkeypatch):
    messages = []
    monkeypatch.setattr("agent.observability.logger.info", messages.append)

    log_event("test", {"key": "value"})

    assert json.loads(messages[0]) == {
        "severity": "INFO",
        "agent_name": "root_agent",
        "event": "test",
        "key": "value",
    }


def test_log_event_uses_error_severity_and_logger_error(monkeypatch):
    info_messages = []
    error_messages = []
    monkeypatch.setattr("agent.observability.logger.info", info_messages.append)
    monkeypatch.setattr("agent.observability.logger.error", error_messages.append)

    log_event("test", {"key": "value"}, severity="ERROR")

    assert info_messages == []
    assert json.loads(error_messages[0])["severity"] == "ERROR"


def test_log_event_redacts_pii_in_fields(monkeypatch):
    messages = []
    monkeypatch.setattr("agent.observability.logger.info", messages.append)

    log_event("signup", {"email": "jane@example.com"})

    assert json.loads(messages[0])["email"] == "[REDACTED_EMAIL]"


def test_instrument_sync_function_returns_value_and_logs_start_and_end(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "agent.observability.logger.info", lambda m: messages.append(json.loads(m))
    )

    @instrument
    def add(a, b):
        return a + b

    result = add(1, 2)

    assert result == 3
    assert [m["event"] for m in messages] == ["add.start", "add.end"]
    assert messages[1]["outcome"] == "success"
    assert "duration_ms" in messages[1]


def test_instrument_sync_function_logs_error_and_reraises(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "agent.observability.logger.info", lambda m: messages.append(json.loads(m))
    )
    monkeypatch.setattr(
        "agent.observability.logger.error", lambda m: messages.append(json.loads(m))
    )

    @instrument
    def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        boom()

    assert [m["event"] for m in messages] == ["boom.start", "boom.error"]
    assert messages[1]["error"] == "nope"
    assert messages[1]["severity"] == "ERROR"


async def test_instrument_async_function_returns_value_and_logs(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "agent.observability.logger.info", lambda m: messages.append(json.loads(m))
    )

    @instrument
    async def fetch(x):
        return x * 2

    result = await fetch(5)

    assert result == 10
    assert [m["event"] for m in messages] == ["fetch.start", "fetch.end"]


def test_instrument_preserves_function_name_and_docstring():
    @instrument
    def documented():
        """A docstring."""
        return None

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "A docstring."


def test_log_model_usage_logs_token_counts(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "agent.observability.logger.info", lambda m: messages.append(json.loads(m))
    )

    class FakeUsage:
        prompt_token_count = 10
        candidates_token_count = 5
        total_token_count = 15

    class FakeEvent:
        usage_metadata = FakeUsage()

    log_model_usage(FakeEvent())

    assert messages == [
        {
            "severity": "INFO",
            "agent_name": "root_agent",
            "event": "model.usage",
            "prompt_tokens": 10,
            "candidates_tokens": 5,
            "total_tokens": 15,
        }
    ]


def test_log_model_usage_noop_without_usage_metadata(monkeypatch):
    messages = []
    monkeypatch.setattr("agent.observability.logger.info", messages.append)

    class FakeEvent:
        pass

    log_model_usage(FakeEvent())

    assert messages == []
