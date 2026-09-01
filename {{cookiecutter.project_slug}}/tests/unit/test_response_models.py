"""Unit tests for Pydantic response models."""

import pytest
from pydantic import ValidationError

from agent.tools.response_models import SearchResult


def test_search_result_valid():
    r = SearchResult(title="Test Title", url="https://example.com", snippet="A snippet")
    assert r.title == "Test Title"
    assert r.url == "https://example.com"
    assert r.snippet == "A snippet"


def test_search_result_missing_snippet_raises():
    with pytest.raises(ValidationError):
        SearchResult(title="T", url="https://example.com")  # type: ignore[call-arg]


def test_search_result_serialises_to_dict():
    r = SearchResult(title="T", url="https://x.com", snippet="S")
    d = r.model_dump()
    assert set(d.keys()) == {"title", "url", "snippet"}


def test_search_result_serialises_to_json():
    r = SearchResult(title="T", url="https://x.com", snippet="S")
    j = r.model_dump_json()
    assert "title" in j
    assert "url" in j
