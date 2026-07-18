import pytest
from typing import List, Optional
from pydantic import BaseModel, Field

from tank import Agent, LLM, tool
from tank.ai.agents import (
    ThoughtStep,
    ToolCallStep,
    ToolResponseStep,
    TextTokenStep,
    FinalResponseStep,
    ValidationErrorStep
)
from tank.ai.memory import SimpleMemory

class Profile(BaseModel):
    name: str = Field(description="Name of the person")
    age: int = Field(gt=0, description="Age of the person, must be positive")

@pytest.mark.asyncio
async def test_response_model_success():
    # Setup agent with response_model
    llm = LLM(provider="mock")
    agent = Agent(llm=llm, response_model=Profile)
    
    steps = []
    async for step in agent.run("Extract profile: Alice is 30 years old."):
        steps.append(step)
        
    # Check steps
    finals = [s for s in steps if isinstance(s, FinalResponseStep)]
    assert len(finals) == 1
    assert isinstance(finals[0].text, Profile)
    assert finals[0].text.name == "Alice"
    assert finals[0].text.age == 30

    # Ensure text token suppression works
    tokens = [s for s in steps if isinstance(s, TextTokenStep)]
    assert len(tokens) == 0


@pytest.mark.asyncio
async def test_response_model_self_correction():
    llm = LLM(provider="mock")
    agent = Agent(llm=llm, response_model=Profile, max_validation_retries=3)
    
    steps = []
    # Sending 'invalid' triggers mock LLM to output age=-5 first, then age=30 on retry
    async for step in agent.run("Extract profile (invalid): Alice is 30 years old."):
        steps.append(step)
        
    # Check steps
    tool_calls = [s for s in steps if isinstance(s, ToolCallStep)]
    tool_responses = [s for s in steps if isinstance(s, ToolResponseStep)]
    thoughts = [s for s in steps if isinstance(s, ThoughtStep)]
    finals = [s for s in steps if isinstance(s, FinalResponseStep)]
    
    # We expect tool call for first (invalid) and second (corrected)
    assert len(tool_calls) == 2
    assert tool_calls[0].name == "__tank_final_answer__"
    assert tool_calls[0].arguments == {"name": "Alice", "age": -5}
    assert tool_calls[1].name == "__tank_final_answer__"
    assert tool_calls[1].arguments == {"name": "Alice", "age": 30}
    
    # We expect tool response with error feedback
    assert len(tool_responses) == 2
    assert "Validation failed" in tool_responses[0].result
    assert "age" in tool_responses[0].result
    
    # We expect retry thoughts
    retry_thoughts = [t for t in thoughts if "Validation failed" in t.thought]
    assert len(retry_thoughts) == 1
    
    # We expect final output to be successfully validated Profile
    assert len(finals) == 1
    assert isinstance(finals[0].text, Profile)
    assert finals[0].text.age == 30

    # Ensure text token suppression works
    tokens = [s for s in steps if isinstance(s, TextTokenStep)]
    assert len(tokens) == 0


@pytest.mark.asyncio
async def test_response_model_exhaustion():
    llm = LLM(provider="mock")
    agent = Agent(llm=llm, response_model=Profile, max_validation_retries=2)
    
    steps = []
    # Sending 'always_invalid' triggers mock LLM to output invalid payload repeatedly
    async for step in agent.run("Extract profile (always_invalid): Alice is 30 years old."):
        steps.append(step)
        
    # We expect ValidationErrorStep at the end
    errors = [s for s in steps if isinstance(s, ValidationErrorStep)]
    finals = [s for s in steps if isinstance(s, FinalResponseStep)]
    
    assert len(errors) == 1
    assert len(finals) == 0
    assert any("age" in err for err in errors[0].errors)

def test_response_model_collision_check():
    @tool
    def __tank_final_answer__(x: int):
        """Reserved tool name collision check."""
        return x
        
    with pytest.raises(ValueError) as excinfo:
        Agent(tools=[__tank_final_answer__])
        
    assert "__tank_final_answer__ is a reserved tool name" in str(excinfo.value)

@pytest.mark.asyncio
async def test_response_model_regression_check():
    # Setup agent with NO response_model
    llm = LLM(provider="mock")
    agent = Agent(llm=llm, response_model=None)
    
    steps = []
    async for step in agent.run("Hello there!"):
        steps.append(step)
        
    # Standard text token streaming must operate correctly
    tokens = [s for s in steps if isinstance(s, TextTokenStep)]
    finals = [s for s in steps if isinstance(s, FinalResponseStep)]
    
    assert len(tokens) > 0
    assert len(finals) == 1
    assert isinstance(finals[0].text, str)
    assert "Mock LLM provider" in finals[0].text
