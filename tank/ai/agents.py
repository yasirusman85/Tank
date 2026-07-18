import json
import asyncio
from typing import List, Dict, Any, AsyncGenerator, Union
from pydantic import BaseModel
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
    text: str

# Unified agent step type
AgentStep = Union[ThoughtStep, ToolCallStep, ToolResponseStep, TextTokenStep, FinalResponseStep]

class Agent:
    llm: LLM = LLM(provider="mock")
    tools: List[Tool] = []
    memory: BaseMemory = SimpleMemory()
    max_iterations: int = 5

    def __init__(
        self,
        llm: LLM | None = None,
        tools: List[Tool] | None = None,
        memory: BaseMemory | None = None,
        max_iterations: int | None = None
    ):
        """
        Allows overriding defaults at instantiation.
        """
        if llm is not None:
            self.llm = llm
        if tools is not None:
            self.tools = tools
        if memory is not None:
            self.memory = memory
        if max_iterations is not None:
            self.max_iterations = max_iterations
            
        # Map tools by name for fast lookup
        self._tools_map = {t.name: t for t in self.tools}

    async def run(self, query: str, session_id: str = "default") -> AsyncGenerator[AgentStep, None]:
        """
        Run the agent execution loop, yielding structured steps and streaming outputs.
        """
        # 1. Fetch conversation history from memory
        messages = await self.memory.get_messages(session_id)
        
        # 2. Add current user query
        user_msg = {"role": "user", "content": query}
        messages.append(user_msg)
        await self.memory.add_message(session_id, user_msg)
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            
            # Accumulators for this specific LLM generation turn
            content_accumulated = []
            thoughts_accumulated = []
            tool_calls_buffered = {}
            
            # 3. Request stream from LLM
            llm_stream = self.llm.astream(messages, tools=self.tools)
            
            async for chunk in llm_stream:
                if isinstance(chunk, LLMThoughtChunk):
                    thoughts_accumulated.append(chunk.thought)
                    yield ThoughtStep(thought=chunk.thought)
                    
                elif isinstance(chunk, LLMTokenChunk):
                    content_accumulated.append(chunk.token)
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
                
            async def run_single_tool(tc_dict):
                t_name = tc_dict["name"]
                t_args = tc_dict["arguments"]
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
                
            # Update messages with the complete session history for the next iteration
            messages = await self.memory.get_messages(session_id)
            
        else:
            # Fallback if loop exceeded max iterations
            yield FinalResponseStep(text="Error: Maximum execution iterations exceeded.")
