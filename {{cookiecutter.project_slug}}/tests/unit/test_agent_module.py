"""Unit tests for agent.py module — test agent initialization."""


def test_agent_module_imports_successfully():
    """Test that the agent module imports without errors."""
    # This test ensures that agent.py can be imported
    # which tests all the module-level code
    from agent import agent  # noqa: F401

    assert True  # If we get here, the import succeeded


def test_root_agent_is_defined():
    """Test that root_agent is properly defined in the agent module."""
    from agent.agent import root_agent

    assert root_agent is not None
    assert hasattr(root_agent, "name")
    assert root_agent.name == "root_agent"


def test_root_agent_has_tools():
    """Test that root_agent has tools configured."""
    from agent.agent import root_agent

    assert hasattr(root_agent, "tools")
    assert root_agent.tools is not None
    assert len(root_agent.tools) > 0


def test_root_agent_has_model():
    """Test that root_agent has a model configured."""
    from agent.agent import root_agent

    assert hasattr(root_agent, "model")
    assert root_agent.model is not None


def test_root_agent_has_instruction():
    """Test that root_agent has instruction text configured."""
    from agent.agent import root_agent

    assert hasattr(root_agent, "instruction")
    assert root_agent.instruction is not None
    assert isinstance(root_agent.instruction, str)
    assert len(root_agent.instruction) > 0
