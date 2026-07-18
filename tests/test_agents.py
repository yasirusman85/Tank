import pytest
from tank.ai.llm import LLM
from tank.ai.tools import tool
from tank.ai.memory import SimpleMemory
from tank.ai.agents import (
    Agent,
    ThoughtStep,
    ToolCallStep,
    ToolResponseStep,
    TextTokenStep,
    FinalResponseStep
)

@pytest.mark.asyncio
async def test_agent_mock_execution_no_tools():
    # Setup LLM with mock provider
    llm = LLM(provider="mock")
    memory = SimpleMemory()
    agent = Agent(llm=llm, tools=[], memory=memory)

    steps = []
    async for step in agent.run("Hello there!", session_id="test_session"):
        steps.append(step)

    # Check that steps are yielded correctly
    assert len(steps) > 0
    
    # Check that we got at least one ThoughtStep, TextTokenStep, and FinalResponseStep
    thoughts = [s for s in steps if isinstance(s, ThoughtStep)]
    tokens = [s for s in steps if isinstance(s, TextTokenStep)]
    finals = [s for s in steps if isinstance(s, FinalResponseStep)]

    assert len(thoughts) > 0
    assert len(tokens) > 0
    assert len(finals) == 1
    assert "Mock LLM provider" in finals[0].text

    # Verify conversation history was updated
    history = await memory.get_messages("test_session")
    assert len(history) == 2  # User query + Assistant response
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello there!"
    assert history[1]["role"] == "assistant"
    assert "Mock LLM provider" in history[1]["content"]

@pytest.mark.asyncio
async def test_agent_mock_execution_with_tools():
    # Setup a weather tool
    @tool
    def get_weather(location: str) -> str:
        """Get the current weather for a location."""
        return f"The weather in {location} is rainy and 60 degrees."

    llm = LLM(provider="mock")
    memory = SimpleMemory()
    agent = Agent(llm=llm, tools=[get_weather], memory=memory)

    steps = []
    async for step in agent.run("What is the weather in San Francisco?", session_id="tool_session"):
        steps.append(step)

    # Check that tool execution steps are in the yielded list
    tool_calls = [s for s in steps if isinstance(s, ToolCallStep)]
    tool_responses = [s for s in steps if isinstance(s, ToolResponseStep)]
    finals = [s for s in steps if isinstance(s, FinalResponseStep)]

    assert len(tool_calls) == 1
    assert tool_calls[0].name == "get_weather"
    assert tool_calls[0].arguments == {"location": "San Francisco"}

    assert len(tool_responses) == 1
    assert tool_responses[0].name == "get_weather"
    assert "rainy" in tool_responses[0].result

    assert len(finals) == 1
    assert "based on tool result: The weather in San Francisco is rainy and 60 degrees" in finals[0].text

    # Verify message sequence in memory
    history = await memory.get_messages("tool_session")
    # Expected sequence:
    # 1. User: What is the weather...
    # 2. Assistant: Tool calls request
    # 3. Tool: Result
    # 4. Assistant: Final response
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert "tool_calls" in history[1]
    assert history[2]["role"] == "tool"
    assert history[3]["role"] == "assistant"
    assert "based on tool result" in history[3]["content"]
