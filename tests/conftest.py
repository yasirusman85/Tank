"""
Shared pytest fixtures for Tank framework test suite.
"""
import pytest
from tank import Tank, Agent, LLM, tool, SimpleMemory


@pytest.fixture
def mock_llm():
    return LLM(provider="mock")


@pytest.fixture
def simple_memory():
    return SimpleMemory()


@pytest.fixture
def test_app():
    return Tank()


@tool
def dummy_tool(query: str) -> str:
    """A dummy tool for testing."""
    return f"Processed {query}"


@pytest.fixture
def sample_agent(mock_llm, simple_memory):
    return Agent(
        llm=mock_llm,
        tools=[dummy_tool],
        memory=simple_memory,
        system_prompt="You are a helpful assistant."
    )
