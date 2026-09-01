"""Unit tests for agent module initialization."""

import pytest

from agent import load_prompt


def test_load_prompt_returns_string():
    """Test that load_prompt returns a string."""
    result = load_prompt("root_agent")
    assert isinstance(result, str)
    assert len(result) > 0


def test_load_prompt_contains_system_prompts():
    """Test that load_prompt includes system prompts."""
    result = load_prompt("root_agent")
    # Should contain content from system prompts (base.md and safety.md)
    assert len(result) > 100  # Expect substantial content


def test_load_prompt_concatenates_with_separator():
    """Test that multiple prompts are joined with separator."""
    result = load_prompt("root_agent")
    # Check for the concatenation separator
    assert "---" in result


def test_load_prompt_invalid_agent_raises_error():
    """Test that loading a non-existent agent raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        load_prompt("nonexistent_agent_xyz")
    assert "No prompts found" in str(exc_info.value)
    assert "nonexistent_agent_xyz" in str(exc_info.value)


def test_load_prompt_root_agent_loads_successfully():
    """Test that root_agent prompt loads without errors."""
    # This should not raise any exceptions
    result = load_prompt("root_agent")
    assert result is not None
    assert isinstance(result, str)
