"""Unit tests for the standalone health check — no network, no GCP credentials required."""
from unittest.mock import Mock

from deployment.scripts.health_check import run_smoke_test


def test_run_smoke_test_passes_when_events_returned():
    remote_agent = Mock()
    remote_agent.stream_query.return_value = iter([{"type": "final_response"}])

    assert run_smoke_test(remote_agent) is True


def test_run_smoke_test_fails_when_no_events_returned():
    remote_agent = Mock()
    remote_agent.stream_query.return_value = iter([])

    assert run_smoke_test(remote_agent) is False


def test_run_smoke_test_passes_message_and_user_id_through():
    remote_agent = Mock()
    remote_agent.stream_query.return_value = iter([{"type": "final_response"}])

    run_smoke_test(remote_agent, message="hello", user_id="tester")

    remote_agent.stream_query.assert_called_once_with(message="hello", user_id="tester")
