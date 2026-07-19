import json
import asyncio
from dataclasses import dataclass, field
from functools import singledispatch
from typing import List, Dict, Any, AsyncGenerator, Union, Optional, Type, Callable

from pydantic import BaseModel, ValidationError
from tank.ai.llm import LLM, LLMThoughtChunk, LLMTokenChunk, LLMToolCallChunk
from tank.ai.tools import Tool
from tank.ai.memory import BaseMemory, SimpleMemory

class ThoughtStep(BaseModel):
    thought: str

class ToolCallStep(BaseModel):
    name: str
    arguments: Dict[str, Any]
    id: str

class ToolResponseStep(BaseModel):
    name: str
    result: Any
    id: str

class TextTokenStep(BaseModel):
    token: str

class FinalResponseStep(BaseModel):
    text: Any  # Can be a string or a validated Pydantic model instance

class ValidationErrorStep(BaseModel):
    errors: List[str]

class ApprovalRequiredStep(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    id: str

class HandoffStep(BaseModel):
    target_agent: str
    reason: str
    session_id: str

# Unified agent step type
AgentStep = Union[ThoughtStep, ToolCallStep, ToolResponseStep, TextTokenStep, FinalResponseStep, ValidationErrorStep, ApprovalRequiredStep, HandoffStep]



@dataclass
class _LLMTurnState:
    content_accumulated: List[str] = field(default_factory=list)
    thoughts_accumulated: List[str] = field(default_factory=list)
    tool_calls_buffered: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@singledispatch
def _handle_llm_chunk(chunk: Any, agent: Any, state: _LLMTurnState) -> Optional[AgentStep]:
    return None


@_handle_llm_chunk.register
def _(chunk: LLMThoughtChunk, agent: Any, state: _LLMTurnState) -> ThoughtStep:
    state.thoughts_accumulated.append(chunk.thought)
    return ThoughtStep(thought=chunk.thought)


@_handle_llm_chunk.register
def _(chunk: LLMTokenChunk, agent: Any, state: _LLMTurnState) -> Optional[TextTokenStep]:
    state.content_accumulated.append(chunk.token)
    if not agent.response_model:
        return TextTokenStep(token=chunk.token)
    return None


@_handle_llm_chunk.register
def _(chunk: LLMToolCallChunk, agent: Any, state: _LLMTurnState) -> None:
    if chunk.id not in state.tool_calls_buffered:
        state.tool_calls_buffered[chunk.id] = {
            "name": chunk.name,
            "arguments_stream": [],
        }
    state.tool_calls_buffered[chunk.id]["arguments_stream"].append(chunk.arguments)
    return None



"""
Agent loop execution, streaming steps, schema validation, and tool approval gates for Tank framework.
"""
class Agent:
    response_model: Optional[Type[BaseModel]] = None
    max_validation_retries: int = 3
    system_prompt: Optional[str] = None

    def _resolve_attr(self, attr_name: str, passed_val: Any, default_factory: Callable[[], Any]):
        if passed_val is not None:
            setattr(self, attr_name, passed_val)
        elif not (hasattr(self, attr_name) and getattr(self, attr_name) is not None):
            setattr(self, attr_name, default_factory())

    def __init__(
        self,
        llm: LLM | None = None,
        tools: List[Tool] | None = None,
        memory: BaseMemory | None = None,
        max_iterations: int | None = None,
        response_model: Optional[Type[BaseModel]] = None,
        max_validation_retries: int | None = None,
        system_prompt: Optional[str] = None
    ):
        """
        Allows overriding defaults at instantiation.
        """
        from tank.core.config import settings

        self._resolve_attr("llm", llm, lambda: LLM())
        self._resolve_attr("tools", tools, lambda: [])
        
        def _default_memory():
            if settings.MEMORY_BACKEND == "sqlalchemy":
                from tank.ai.memory import SQLAlchemyMemory
                return SQLAlchemyMemory(db_url=settings.DATABASE_URL)
            return SimpleMemory()
            
        self._resolve_attr("memory", memory, _default_memory)
        self._resolve_attr("max_iterations", max_iterations, lambda: 5)
        self._resolve_attr("response_model", response_model, lambda: None)
        self._resolve_attr("max_validation_retries", max_validation_retries, lambda: 3)
        self._resolve_attr("system_prompt", system_prompt, lambda: None)
            
        # Collision Guard for reserved tool name

        for t in self.tools:
            if t.name == "__tank_final_answer__":
                raise ValueError("__tank_final_answer__ is a reserved tool name.")

        # Map tools by name for fast lookup
        self._tools_map = {t.name: t for t in self.tools}



    async def run(self, query: str, session_id: str = "default") -> AsyncGenerator[AgentStep, None]:
        """
        Run the agent execution loop, yielding structured steps and streaming outputs.
        """
        # 1. Fetch conversation history from memory
        messages = await self.memory.get_messages(session_id)
        
        # If history is empty and self.system_prompt is set, prepend it
        if not messages and self.system_prompt:
            sys_msg = {"role": "system", "content": self.system_prompt}
            await self.memory.add_message(session_id, sys_msg)
            messages = [sys_msg]
            
        # 2. Add current user query
        user_msg = {"role": "user", "content": query}
        messages.append(user_msg)
        await self.memory.add_message(session_id, user_msg)
        
        # 3. Delegate to the execute loop
        async for step in self._execute_loop(session_id):
            yield step

    async def resume(
        self,
        session_id: str,
        tool_call_id: str,
        approved: bool,
        user_feedback: Optional[str] = None
    ) -> AsyncGenerator[AgentStep, None]:
        """
        Resume a paused agent execution by providing confirmation for a pending tool call.
        """
        # 1. Fetch conversation history from memory
        messages = await self.memory.get_messages(session_id)
        if not messages:
            raise ValueError(f"No conversation history found for session '{session_id}'.")
            
        # 2. Locate the last assistant message containing the pending tool call
        last_assistant_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                last_assistant_msg = msg
                break
                
        if not last_assistant_msg:
            raise ValueError(f"No pending tool calls found in session '{session_id}'.")
            
        # Find the target tool call by ID
        target_tc = None
        for tc in last_assistant_msg["tool_calls"]:
            if tc.get("id") == tool_call_id:
                target_tc = tc
                break
                
        if not target_tc:
            raise ValueError(f"No pending tool call found matching id '{tool_call_id}'.")
            
        # 3. Execute or reject the tool call
        tc_name = target_tc["name"]
        tc_args = target_tc["arguments"]
        
        if approved:
            # Execute the tool
            if tc_name == "__tank_final_answer__":
                try:
                    validated = self.response_model.model_validate(tc_args)
                    result = "Success"
                    yield FinalResponseStep(text=validated)
                except ValidationError as ve:
                    error_msgs = [f"Field '{'.'.join(str(x) for x in err['loc'])}': {err['msg']}" for err in ve.errors()]
                    result = f"Error: Validation failed. {'; '.join(error_msgs)}. Please call '__tank_final_answer__' again with corrected parameters."
            else:
                tool_obj = self._tools_map.get(tc_name)
                if not tool_obj:
                    result = f"Error: Tool '{tc_name}' is not registered."
                else:
                    try:
                        result = await tool_obj(**tc_args)
                    except Exception as e:
                        result = f"Error: {str(e)}"
        else:
            # Rejection feedback
            feedback = user_feedback or "User denied approval."
            result = f"Error: User denied approval. {feedback}"
            
        # 4. Yield ToolResponseStep and record message in memory
        yield ToolResponseStep(name=tc_name, result=result, id=tool_call_id)
        
        tool_msg = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tc_name,
            "content": str(result)
        }
        await self.memory.add_message(session_id, tool_msg)
        
        # 5. Check if there are other pending tool calls in this turn that still require approval
        messages = await self.memory.get_messages(session_id)
        # Find all tool responses for this turn
        responses_by_id = {msg.get("tool_call_id") for msg in messages if msg.get("role") == "tool"}
        
        pending_approvals = []
        for tc in last_assistant_msg["tool_calls"]:
            if tc.get("id") not in responses_by_id:
                t_obj = self._tools_map.get(tc["name"])
                if t_obj and getattr(t_obj, "requires_approval", False):
                    pending_approvals.append(tc)
                    
        if pending_approvals:
            # Yield remaining approvals and stay paused
            for tc in pending_approvals:
                yield ApprovalRequiredStep(tool_name=tc["name"], arguments=tc["arguments"], id=tc["id"])
            return
            
        # 6. If no more pending tool calls, continue the execution loop!
        async for step in self._execute_loop(session_id):
            yield step

    async def _execute_loop(self, session_id: str) -> AsyncGenerator[AgentStep, None]:
        """
        Internal execution loop that runs the LLM generation and tool execution.
        """
        messages = await self.memory.get_messages(session_id)
        
        # Setup final response tool dynamically if response_model is defined
        active_tools = list(self.tools)
        if self.response_model:
            def final_answer_dummy(**kwargs):
                return kwargs
            final_answer_tool = Tool(
                func=final_answer_dummy,
                name="__tank_final_answer__",
                description=f"Deliver the final structured output conforming to the {self.response_model.__name__} schema."
            )
            final_answer_tool.args_model = self.response_model
            active_tools.append(final_answer_tool)
            self._tools_map["__tank_final_answer__"] = final_answer_tool

        validation_failures = 0
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            
            # Accumulators for this specific LLM generation turn
            turn_state = _LLMTurnState()
            
            # Format system instructions if response_model is active
            messages_to_send = [dict(m) for m in messages]
            if self.response_model:
                schema_instruction = f"\nYou MUST deliver your final response by calling the tool '__tank_final_answer__' with arguments matching the schema."
                system_found = False
                for msg in messages_to_send:
                     if msg.get("role") == "system":
                         msg["content"] = str(msg.get("content", "")) + schema_instruction
                         system_found = True
                         break
                if not system_found:
                     messages_to_send.insert(0, {"role": "system", "content": schema_instruction})

            # Request stream from LLM
            llm_stream = self.llm.astream(messages_to_send, tools=active_tools)
            
            async for chunk in llm_stream:
                step = _handle_llm_chunk(chunk, self, turn_state)
                if step:
                    yield step

            # If no tool calls were requested, the execution turn is complete
            if not turn_state.tool_calls_buffered:
                assistant_content = "".join(turn_state.content_accumulated)
                assistant_thought = "".join(turn_state.thoughts_accumulated)
                
                assistant_msg = {"role": "assistant"}
                if assistant_content:
                    assistant_msg["content"] = assistant_content
                if assistant_thought:
                    assistant_msg["thought"] = assistant_thought
                    
                await self.memory.add_message(session_id, assistant_msg)
                
                if self.response_model:
                    validation_failures += 1
                    error_msg = "Error: You did not call the '__tank_final_answer__' tool to deliver your final response. Please retry and call '__tank_final_answer__'."
                    if validation_failures >= self.max_validation_retries:
                        yield ValidationErrorStep(errors=[error_msg])
                        break
                    else:
                        yield ThoughtStep(thought="Agent failed to return structured response. Retrying...")
                        fake_tool_call_id = f"fake_call_{iteration}"
                        # Save fake assistant tool call request in history to satisfy OpenAI contiguous message rules
                        await self.memory.add_message(session_id, {
                            "role": "assistant",
                            "tool_calls": [{"id": fake_tool_call_id, "name": "__tank_final_answer__", "arguments": {}}]
                        })
                        await self.memory.add_message(session_id, {
                            "role": "tool",
                            "tool_call_id": fake_tool_call_id,
                            "name": "__tank_final_answer__",
                            "content": error_msg
                        })
                        messages = await self.memory.get_messages(session_id)
                        continue
                else:
                    yield FinalResponseStep(text=assistant_content)
                    break
                
            # Process tool calls
            tool_calls_to_run = []
            for tc_id, tc_data in turn_state.tool_calls_buffered.items():
                args_str = "".join(tc_data["arguments_stream"])
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}
                
                tool_calls_to_run.append({
                    "id": tc_id,
                    "name": tc_data["name"],
                    "arguments": args
                })
                
            # Save assistant tool call request to memory
            assistant_content = "".join(turn_state.content_accumulated)
            assistant_thought = "".join(turn_state.thoughts_accumulated)
            assistant_msg = {
                "role": "assistant",
                "tool_calls": tool_calls_to_run
            }
            if assistant_content:
                assistant_msg["content"] = assistant_content
            if assistant_thought:
                assistant_msg["thought"] = assistant_thought
                
            await self.memory.add_message(session_id, assistant_msg)
            
            # Yield all ToolCallSteps first
            for tc in tool_calls_to_run:
                yield ToolCallStep(name=tc["name"], arguments=tc["arguments"], id=tc["id"])
                
            # Separate tool calls by requires_approval attribute
            pending_approvals = []
            normal_calls = []
            for tc in tool_calls_to_run:
                t_obj = self._tools_map.get(tc["name"])
                if t_obj and getattr(t_obj, "requires_approval", False):
                    pending_approvals.append(tc)
                else:
                    normal_calls.append(tc)

            # Intercept __tank_final_answer__ validation at runtime
            final_answer_val_step = None
            final_answer_val_error = None
            final_answer_tc_id = None
            
            async def run_single_tool(tc_dict):
                t_name = tc_dict["name"]
                t_args = tc_dict["arguments"]
                
                if t_name == "__tank_final_answer__":
                    nonlocal final_answer_tc_id, final_answer_val_step, final_answer_val_error
                    final_answer_tc_id = tc_dict["id"]
                    try:
                        validated = self.response_model.model_validate(t_args)
                        final_answer_val_step = FinalResponseStep(text=validated)
                        return "Success"
                    except ValidationError as ve:
                        error_msgs = []
                        for err in ve.errors():
                            loc = ".".join(str(x) for x in err["loc"])
                            msg = err["msg"]
                            error_msgs.append(f"Field '{loc}': {msg}")
                        final_answer_val_error = error_msgs
                        return f"Error: Validation failed. {'; '.join(error_msgs)}. Please call '__tank_final_answer__' again with corrected parameters."
                
                tool_obj = self._tools_map.get(t_name)
                if not tool_obj:
                    return f"Error: Tool '{t_name}' is not registered. Please retry with correct inputs."
                try:
                    return await tool_obj(**t_args)
                except Exception as e:
                    return f"Error: {str(e)} Please retry with correct inputs."

            # Run all normal tools concurrently
            tasks = [run_single_tool(tc) for tc in normal_calls]
            results = await asyncio.gather(*tasks)

            # Yield responses and append to memory for normal tools
            for tc, result in zip(normal_calls, results):
                yield ToolResponseStep(name=tc["name"], result=result, id=tc["id"])
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": str(result)
                }
                await self.memory.add_message(session_id, tool_msg)

            # Check if final answer was validated or failed
            if final_answer_tc_id:
                if final_answer_val_step:
                    yield final_answer_val_step
                    break
                elif final_answer_val_error:
                    validation_failures += 1
                    if validation_failures >= self.max_validation_retries:
                        yield ValidationErrorStep(errors=final_answer_val_error)
                        break
                    else:
                        yield ThoughtStep(thought=f"Validation failed (attempt {validation_failures}/{self.max_validation_retries}): {'; '.join(final_answer_val_error)}. Retrying...")

            # Yield remaining approvals and pause the loop execution!
            if pending_approvals:
                for tc in pending_approvals:
                    yield ApprovalRequiredStep(tool_name=tc["name"], arguments=tc["arguments"], id=tc["id"])
                return  # Exits generator, leaving state paused until resume() is called

            # Update messages with the complete session history for the next iteration
            messages = await self.memory.get_messages(session_id)
            
        else:
            if self.response_model:
                yield ValidationErrorStep(errors=["Error: Maximum execution iterations reached without resolving schema validation."])
            else:
                yield FinalResponseStep(text="Error: Maximum execution iterations exceeded.")
