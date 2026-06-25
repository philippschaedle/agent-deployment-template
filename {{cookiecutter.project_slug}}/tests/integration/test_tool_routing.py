"""Integration tests for tool registration and agent wiring.

These tests verify that tools are correctly registered with root_agent and
that the agent's instruction text is fully assembled from all prompt files.
They do not test individual tool logic (that lives in tests/unit/test_tools.py).

What is tested here:
  - Specific tools are registered in root_agent.tools
  - Every registered tool is callable
  - The assembled instruction contains content from system and task prompt files
"""


def test_datetime_tool_is_registered():
    """get_current_datetime is explicitly registered in root_agent.tools."""
    from agent.agent import root_agent
    from agent.tools.example_tools import get_current_datetime

    assert get_current_datetime in root_agent.tools


def test_search_tool_is_registered():
    """web_search is explicitly registered in root_agent.tools."""
    from agent.agent import root_agent
    from agent.tools.example_tools import web_search

    assert web_search in root_agent.tools


def test_all_registered_tools_are_callable():
    """Every entry in root_agent.tools is a callable function."""
    from agent.agent import root_agent

    for tool in root_agent.tools:
        assert callable(tool), (
            f"Expected a callable tool, got {type(tool).__name__}: {tool!r}"
        )


def test_at_least_two_tools_registered():
    """root_agent has at least the two built-in tools (more can be added)."""
    from agent.agent import root_agent

    assert len(root_agent.tools) >= 2, (
        f"Expected ≥2 tools, found {len(root_agent.tools)}: {root_agent.tools}"
    )


def test_instruction_includes_safety_guidelines():
    """root_agent instruction includes safety content from prompts/system/safety.md."""
    from agent.agent import root_agent

    instruction = root_agent.instruction
    assert isinstance(instruction, str), "Instruction must be a string"
    instruction_lower = instruction.lower()
    safety_keywords = ("safe", "harm", "refuse", "cannot", "policy")
    assert any(kw in instruction_lower for kw in safety_keywords), (
        "Instruction must contain safety guidelines. "
        f"Looked for any of {safety_keywords!r} in the assembled instruction."
    )


def test_instruction_is_substantive():
    """root_agent instruction is long enough to contain all prompt files."""
    from agent.agent import root_agent

    # base.md + safety.md + example_task.md should add up to >200 chars
    instruction = root_agent.instruction
    assert isinstance(instruction, str), "Instruction must be a string"
    assert len(instruction) > 200, (
        "Instruction appears too short — ensure all prompt files in "
        "prompts/prompts.yaml are loaded correctly."
    )


def test_instruction_contains_section_separator():
    """Prompt sections are joined with the expected separator (---)."""
    from agent.agent import root_agent

    # load_prompt() uses "\n\n---\n\n" between sections
    instruction = root_agent.instruction
    assert isinstance(instruction, str), "Instruction must be a string"
    assert "---" in instruction, (
        "Instruction is missing the section separator — "
        "check that load_prompt() is concatenating multiple prompt files."
    )
