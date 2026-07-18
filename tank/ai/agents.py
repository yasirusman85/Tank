import json
import asyncio
from typing import List, Dict, Any, AsyncGenerator, Union, Optional, Type
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

# Unified agent step type
AgentStep = Union[ThoughtStep, ToolCallStep, ToolResponseStep, TextTokenStep, FinalResponseStep, ValidationErrorStep]


class Agent:
    response_model: Optional[Type[BaseModel]] = None
    max_validation_retries: int = 3
    system_prompt: Optional[str] = None

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
        
        # 1. Resolve LLM
        if llm is not None:
            self.llm = llm
        elif hasattr(self, 'llm') and self.llm is not None:
            pass
        else:
            self.llm = LLM()
            
        # 2. Resolve tools
        if tools is not None:
            self.tools = tools
        elif hasattr(self, 'tools') and self.tools is not None:
            pass
        else:
            self.tools = []
            
        # 3. Resolve memory
        if memory is not None:
            self.memory = memory
        elif hasattr(self, 'memory') and self.memory is not None:
            pass
        else:
            if settings.MEMORY_BACKEND == "sqlalchemy":
                from tank.ai.memory import SQLAlchemyMemory
                self.memory = SQLAlchemyMemory(db_url=settings.DATABASE_URL)
            else:
                self.memory = SimpleMemory()
                
        # 4. Resolve max iterations
        if max_iterations is not None:
            self.max_iterations = max_iterations
        elif hasattr(self, 'max_iterations') and self.max_iterations is not None:
            pass
        else:
            self.max_iterations = 5

        # 5. Resolve response_model
        if response_model is not None:
            self.response_model = response_model
        elif hasattr(self, 'response_model') and self.response_model is not None:
            pass
        else:
            self.response_model = None

        # 6. Resolve max_validation_retries
        if max_validation_retries is not None:
            self.max_validation_retries = max_validation_retries
        elif hasattr(self, 'max_validation_retries') and self.max_validation_retries is not None:
            pass
        else:
            self.max_validation_retries = 3

        # 7. Resolve system_prompt
        if system_prompt is not None:
            self.system_prompt = system_prompt
        elif hasattr(self, 'system_prompt') and self.system_prompt is not None:
            pass
        else:
            self.system_prompt = None
            
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
            content_accumulated = []
            thoughts_accumulated = []
            tool_calls_buffered = {}
            
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

            # 3. Request stream from LLM
            llm_stream = self.llm.astream(messages_to_send, tools=active_tools)
            
            async for chunk in llm_stream:
                if isinstance(chunk, LLMThoughtChunk):
                    thoughts_accumulated.append(chunk.thought)
                    yield ThoughtStep(thought=chunk.thought)
                    
                elif isinstance(chunk, LLMTokenChunk):
                    content_accumulated.append(chunk.token)
                    # Suppress raw text tokens from being streamed to the user if response_model is active
                    if not self.response_model:
                        yield TextTokenStep(token=chunk.token)
                    
                elif isinstance(chunk, LLMToolCallChunk):
                    # Buffer the tool call arguments as they stream in
                    tc_id = chunk.id
                    if tc_id not in tool_calls_buffered:
                        tool_calls_buffered[tc_id] = {
                            "name": chunk.name,
                            "arguments_stream": []
                        }
                    tool_calls_buffered[tc_id]["arguments_stream"].append(chunk.arguments)

            # 4. If no tool calls were requested, the execution turn is complete
            if not tool_calls_buffered:
                assistant_content = "".join(content_accumulated)
                assistant_thought = "".join(thoughts_accumulated)
                
                assistant_msg = {"role": "assistant"}
                if assistant_content:
                    assistant_msg["content"] = assistant_content
                if assistant_thought:
                    assistant_msg["thought"] = assistant_thought
                    
                await self.memory.add_message(session_id, assistant_msg)
                
                if self.response_model:
                    # The model was instructed to use __tank_final_answer__ but did not.
                    # This is treated as a validation failure (did not call tool).
                    validation_failures += 1
                    error_msg = "Error: You did not call the '__tank_final_answer__' tool to deliver your final response. Please retry and call '__tank_final_answer__'."
                    if validation_failures >= self.max_validation_retries:
                        yield ValidationErrorStep(errors=[error_msg])
                        break
                    else:
                        yield ThoughtStep(thought="Agent failed to return structured response. Retrying...")
                        # INTENTIONALLY SYNTHETIC: Append a fake tool call and response in history to prompt the LLM
                        # to self-correct when it skipped calling the hidden validation tool.
                        fake_tool_call_id = f"fake_call_{iteration}"
                        # Save fake assistant tool call request in history to satisfy OpenAI contiguous message rules
                        await self.memory.add_message(session_id, {
                            "role": "assistant",
                            "tool_calls": [{"id": fake_tool_call_id, "name": "__tank_final_answer__", "arguments": {}}]
                        })
                        # Save tool error response to prompt the self-correction
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
                
            # 5. Process tool calls
            tool_calls_to_run = []
            for tc_id, tc_data in tool_calls_buffered.items():
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
            assistant_content = "".join(content_accumulated)
            assistant_thought = "".join(thoughts_accumulated)
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
                
            # Intercept __tank_final_answer__ validation at runtime
            final_answer_val_step = None
            final_answer_val_error = None
            final_answer_tc_id = None
            
            async def run_single_tool(tc_dict):
                t_name = tc_dict["name"]
                t_args = tc_dict["arguments"]
                
                if t_name == "__tank_final_answer__":
                    # Perform schema validation
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

            # Run all tools concurrently
            tasks = [run_single_tool(tc) for tc in tool_calls_to_run]
            results = await asyncio.gather(*tasks)

            # Yield responses and append to memory
            for tc, result in zip(tool_calls_to_run, results):
                yield ToolResponseStep(name=tc["name"], result=result, id=tc["id"])
                
                # Append tool response to memory
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
                    # Successful validation!
                    yield final_answer_val_step
                    break
                elif final_answer_val_error:
                    validation_failures += 1
                    if validation_failures >= self.max_validation_retries:
                        yield ValidationErrorStep(errors=final_answer_val_error)
                        break
                    else:
                        yield ThoughtStep(thought=f"Validation failed (attempt {validation_failures}/{self.max_validation_retries}): {'; '.join(final_answer_val_error)}. Retrying...")
                
            # Update messages with the complete session history for the next iteration
            messages = await self.memory.get_messages(session_id)
            
        else:
            # Fallback if loop exceeded max iterations
            if self.response_model:
                yield ValidationErrorStep(errors=["Error: Maximum execution iterations reached without resolving schema validation."])
            else:
                yield FinalResponseStep(text="Error: Maximum execution iterations exceeded.")

