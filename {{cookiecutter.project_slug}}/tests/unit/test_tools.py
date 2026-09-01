"""Unit tests for agent tools — no network, no GCP credentials required."""

import json
from unittest.mock import Mock, patch

from agent.tools.example_tools import _serpapi_search, get_current_datetime, web_search
from agent.tools.response_models import SearchResult


def test_get_current_datetime_returns_iso_string():
    result = get_current_datetime()
    assert isinstance(result, str)
    assert "T" in result
    assert "Z" in result or "+" in result  # timezone present


def test_get_current_datetime_is_utc():
    result = get_current_datetime()
    # ISO format with UTC offset ends in +00:00 or Z
    assert result.endswith("+00:00") or result.endswith("Z")


def test_web_search_stub_returns_results(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    results = web_search("test query")
    assert len(results) >= 1
    assert isinstance(results[0], SearchResult)


def test_web_search_stub_contains_query_in_snippet(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    results = web_search("hello world")
    assert "hello world" in results[0].snippet


def test_web_search_result_has_required_fields(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    results = web_search("anything")
    r = results[0]
    assert r.title
    assert r.url
    assert r.snippet


def test_web_search_with_api_key_set(monkeypatch):
    """Test that web_search calls _serpapi_search when SERPAPI_API_KEY is set."""
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-123")
    with patch("agent.tools.example_tools._serpapi_search") as mock_search:
        mock_search.return_value = [
            SearchResult(
                title="Mocked Result", url="https://example.com", snippet="Mock snippet"
            )
        ]
        results = web_search("test query")
        mock_search.assert_called_once_with("test query", "test-key-123")
        assert len(results) == 1
        assert results[0].title == "Mocked Result"


def test_serpapi_search_returns_results():
    """Test _serpapi_search function with mocked urlopen."""
    mock_response_data = {
        "organic_results": [
            {
                "title": "Test Result 1",
                "link": "https://example1.com",
                "snippet": "Snippet 1",
            },
            {
                "title": "Test Result 2",
                "link": "https://example2.com",
                "snippet": "Snippet 2",
            },
        ]
    }

    mock_response = Mock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=None)

    with patch("urllib.request.urlopen", return_value=mock_response):
        results = _serpapi_search("test query", "test-api-key")

        assert len(results) == 2
        assert results[0].title == "Test Result 1"
        assert results[0].url == "https://example1.com"
        assert results[0].snippet == "Snippet 1"
        assert results[1].title == "Test Result 2"
