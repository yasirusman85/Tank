import pytest
from typing import Dict, Any, List

from tank import Agent, LLM, tool
from tank.ai.agents import (
    ThoughtStep,
    ToolCallStep,
    ToolResponseStep,
    FinalResponseStep,
    ApprovalRequiredStep
)
from tank.ai.memory import SimpleMemory

# Track sensitive tool call executions
sensitive_execution_count = 0

@tool(requires_approval=True)
def sensitive_action(target: str) -> str:
    """A sensitive action that requires user confirmation."""
    global sensitive_execution_count
    sensitive_execution_count += 1
    return f"Sensitive action completed on {target}"

@pytest.mark.asyncio
async def test_approval_gate_pausing_and_resume():
    global sensitive_execution_count
    sensitive_execution_count = 0
    
    llm = LLM(provider="mock")
    memory = SimpleMemory()
    agent = Agent(llm=llm, tools=[sensitive_action], memory=memory)
    
    # 1. Run initial execution
    steps = []
    session_id = "test_hitl_session"
    async for step in agent.run("Perform sensitive action.", session_id=session_id):
        steps.append(step)
        
    # Check that it paused on ApprovalRequiredStep
    approvals = [s for s in steps if isinstance(s, ApprovalRequiredStep)]
    tool_calls = [s for s in steps if isinstance(s, ToolCallStep)]
    tool_responses = [s for s in steps if isinstance(s, ToolResponseStep)]
    finals = [s for s in steps if isinstance(s, FinalResponseStep)]
    
    assert len(approvals) == 1
    assert approvals[0].tool_name == "sensitive_action"
    assert approvals[0].arguments == {"target": "test"}
    assert approvals[0].id == "call_sensitive"
    
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "call_sensitive"
    
    # Verify the actual tool was NOT executed yet
    assert len(tool_responses) == 0
    assert len(finals) == 0
    assert sensitive_execution_count == 0
    
    # 2. Resume with approved=True
    resume_steps = []
    async for step in agent.resume(session_id=session_id, tool_call_id="call_sensitive", approved=True):
        resume_steps.append(step)
        
    resume_responses = [s for s in resume_steps if isinstance(s, ToolResponseStep)]
    resume_finals = [s for s in resume_steps if isinstance(s, FinalResponseStep)]
    
    # Verify tool response was yielded and target function executed
    assert len(resume_responses) == 1
    assert resume_responses[0].name == "sensitive_action"
    assert "completed on test" in resume_responses[0].result
    assert sensitive_execution_count == 1
    
    # Verify LLM generation proceeded to final summary turn
    assert len(resume_finals) == 1
    assert "Sensitive action completed" in resume_finals[0].text

@pytest.mark.asyncio
async def test_approval_gate_rejection():
    global sensitive_execution_count
    sensitive_execution_count = 0
    
    llm = LLM(provider="mock")
    memory = SimpleMemory()
    agent = Agent(llm=llm, tools=[sensitive_action], memory=memory)
    
    # 1. Run initial execution
    session_id = "test_hitl_reject"
    async for _ in agent.run("Perform sensitive action.", session_id=session_id):
        pass
        
    assert sensitive_execution_count == 0
    
    # 2. Resume with approved=False (rejected)
    resume_steps = []
    async for step in agent.resume(
        session_id=session_id, 
        tool_call_id="call_sensitive", 
        approved=False,
        user_feedback="Too risky"
    ):
        resume_steps.append(step)
        
    resume_responses = [s for s in resume_steps if isinstance(s, ToolResponseStep)]
    resume_finals = [s for s in resume_steps if isinstance(s, FinalResponseStep)]
    
    # Tool response should contain rejection information
    assert len(resume_responses) == 1
    assert "User denied approval" in resume_responses[0].result
    assert "Too risky" in resume_responses[0].result
    # Function was NOT called
    assert sensitive_execution_count == 0
    
    # The LLM completed based on rejection feedback
    assert len(resume_finals) == 1
    assert "denied" in resume_finals[0].text or "sensitive_action" in resume_finals[0].text
