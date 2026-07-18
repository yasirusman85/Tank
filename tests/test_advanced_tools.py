import pytest
import time
import asyncio
from pydantic import BaseModel

from tank import Agent, tool, LLM
from tank.ai.llm import LLMThoughtChunk, LLMTokenChunk, LLMToolCallChunk
from tank.ai.agents import ToolCallStep, ToolResponseStep

# =====================================================================
# Docstring Parsing Tests
# =====================================================================

def test_docstring_parsing_google():
    """
    Verify parsing of Google-style docstring parameter descriptions.
    """
    @tool
    def google_tool(x: int, y: str = "default"):
        """
        A tool with Google-style docstring.
        
        Args:
            x (int): The x coordinate.
            y: The name description.
        """
        return f"{x}-{y}"
        
    schema = google_tool.to_json_schema()
    properties = schema["function"]["parameters"]["properties"]
    assert properties["x"]["description"] == "The x coordinate."
    assert properties["y"]["description"] == "The name description."

def test_docstring_parsing_sphinx():
    """
    Verify parsing of Sphinx-style docstring parameter descriptions.
    """
    @tool
    def sphinx_tool(a: float, b: bool):
        """
        A tool with Sphinx-style docstring.
        
        :param a: The float parameter.
        :param b: The boolean parameter.
        """
        return f"{a}-{b}"
        
    schema = sphinx_tool.to_json_schema()
    properties = schema["function"]["parameters"]["properties"]
    assert properties["a"]["description"] == "The float parameter."
    assert properties["b"]["description"] == "The boolean parameter."

def test_docstring_parsing_nested_schema():
    """
    Verify parsing works correctly when an argument is a nested Pydantic model.
    """
    class UserConfig(BaseModel):
        username: str
        role: str

    @tool
    def nested_tool(config: UserConfig, debug: bool = False):
        """
        A tool taking a nested config schema.
        
        Args:
            config: The nested config model object.
            debug: Whether to print debugging logs.
        """
        return f"{config.username}-{debug}"
        
    schema = nested_tool.to_json_schema()
    properties = schema["function"]["parameters"]["properties"]
    assert properties["config"]["description"] == "The nested config model object."
    assert properties["debug"]["description"] == "Whether to print debugging logs."
    parameters = schema["function"]["parameters"]
    assert "$ref" in properties["config"]
    assert "UserConfig" in parameters["$defs"]
    assert "properties" in parameters["$defs"]["UserConfig"]

# =====================================================================
# Parallel Execution Tests
# =====================================================================

@tool
async def slow_tool_1() -> str:
    """Slow tool 1."""
    await asyncio.sleep(0.3)
    return "done 1"

@tool
async def slow_tool_2() -> str:
    """Slow tool 2."""
    await asyncio.sleep(0.3)
    return "done 2"

class ParallelMockLLM(LLM):
    """
    Mock LLM that requests two slow tool calls in a single turn.
    """
    def __init__(self):
        super().__init__(provider="mock")
        
    async def astream(self, messages, tools=None):
        last_message = messages[-1] if messages else None
        if last_message and last_message.get("role") == "tool":
            yield LLMTokenChunk(token="Both tools executed successfully.")
        else:
            yield LLMThoughtChunk(thought="Requesting both tools concurrently.")
            await asyncio.sleep(0.01)
            yield LLMToolCallChunk(name="slow_tool_1", arguments="{}", id="call_1")
            yield LLMToolCallChunk(name="slow_tool_2", arguments="{}", id="call_2")

@pytest.mark.asyncio
async def test_parallel_tool_execution():
    """
    Verify that tools run in parallel and save time (should take less than 0.5s instead of 0.6s+).
    """
    agent = Agent(
        llm=ParallelMockLLM(),
        tools=[slow_tool_1, slow_tool_2]
    )
    
    start_time = time.time()
    steps = []
    async for step in agent.run("Run parallel tools"):
        steps.append(step)
    end_time = time.time()
    
    duration = end_time - start_time
    # Parallel execution of two 0.3s sleep tools should be completed in around 0.3s-0.4s
    assert duration < 0.5, f"Tools ran sequentially, took {duration:.2f}s instead of <0.5s"
    
    # Check that tool call logs were emitted and completed
    call_ids = [s.id for s in steps if isinstance(s, ToolCallStep)]
    assert "call_1" in call_ids
    assert "call_2" in call_ids
    
    responses = {s.name: s.result for s in steps if isinstance(s, ToolResponseStep)}
    assert responses["slow_tool_1"] == "done 1"
    assert responses["slow_tool_2"] == "done 2"

# =====================================================================
# Self-Correction Tests
# =====================================================================

@tool
def check_positive(val: int) -> str:
    """
    Validates if value is positive.
    
    Args:
        val: The value to validate.
    """
    if val <= 0:
        raise ValueError(f"Parameter 'val' must be > 0. Received {val}.")
    return f"Success: {val}"

class SelfCorrectionMockLLM(LLM):
    """
    Mock LLM that triggers an invalid tool call first, and then fixes it
    upon receiving the error message.
    """
    def __init__(self):
        super().__init__(provider="mock")
        
    async def astream(self, messages, tools=None):
        last_message = messages[-1] if messages else None
        
        # Check if the last message is a tool response with an error
        if last_message and last_message.get("role") == "tool":
            content = last_message.get("content", "")
            if "Error:" in content:
                # The LLM sees the error message and yields a corrected call
                yield LLMThoughtChunk(thought="Correcting the input to positive.")
                await asyncio.sleep(0.01)
                yield LLMToolCallChunk(name="check_positive", arguments='{"val": 5}', id="call_corrected")
            else:
                yield LLMThoughtChunk(thought="Successful execution.")
                await asyncio.sleep(0.01)
                yield LLMTokenChunk(token="The final number check is done.")
        else:
            # First turn: yield an invalid argument (negative value)
            yield LLMThoughtChunk(thought="Checking if -5 is positive.")
            await asyncio.sleep(0.01)
            yield LLMToolCallChunk(name="check_positive", arguments='{"val": -5}', id="call_invalid")

@pytest.mark.asyncio
async def test_agent_self_correction():
    """
    Verify that agent catches tool validation errors, returns formatted error
    results to LLM, and allows LLM to try again and self-correct inputs.
    """
    agent = Agent(
        llm=SelfCorrectionMockLLM(),
        tools=[check_positive]
    )
    
    steps = []
    async for step in agent.run("Verify self correction"):
        steps.append(step)
        
    # We expect 2 tool response steps (one failure, one success)
    tool_responses = [s for s in steps if isinstance(s, ToolResponseStep)]
    assert len(tool_responses) == 2
    
    # First tool response should be the formatted error
    assert tool_responses[0].id == "call_invalid"
    assert "Error:" in tool_responses[0].result
    assert "must be > 0. Received -5." in tool_responses[0].result
    assert "Please retry with correct inputs." in tool_responses[0].result
    
    # Second tool response should be successful
    assert tool_responses[1].id == "call_corrected"
    assert tool_responses[1].result == "Success: 5"
