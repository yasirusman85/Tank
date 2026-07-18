import os
import json
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator, Union
from pydantic import BaseModel

class LLMTokenChunk(BaseModel):
    token: str

class LLMThoughtChunk(BaseModel):
    thought: str

class LLMToolCallChunk(BaseModel):
    name: str
    arguments: str
    id: str

# Define types for unified streaming outputs
LLMStreamChunk = Union[LLMTokenChunk, LLMThoughtChunk, LLMToolCallChunk]

class LLM:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        **kwargs
    ):
        """
        Initialize the LLM provider interface.
        provider: 'mock', 'openai', or 'anthropic'
        """
        from tank.core.config import settings
        self.provider = (provider or settings.DEFAULT_PROVIDER or "mock").lower()
        self.model = model or settings.DEFAULT_MODEL or self._get_default_model(self.provider)
        self.api_key = api_key or self._get_api_key(self.provider)
        self.kwargs = kwargs

    def _get_default_model(self, provider: str) -> str:
        if provider == "openai":
            return "gpt-4o"
        elif provider == "anthropic":
            return "claude-3-5-sonnet-20241022"
        return "mock-model"

    def _get_api_key(self, provider: str) -> Optional[str]:
        from tank.core.config import settings
        if provider == "openai":
            return settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic":
            return settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
        return None


    async def astream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Any] | None = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Stream LLM responses including tokens, thoughts, and tool call requests.
        """
        if self.provider == "mock":
            async for chunk in self._astream_mock(messages, tools):
                yield chunk
        elif self.provider == "openai":
            async for chunk in self._astream_openai(messages, tools):
                yield chunk
        elif self.provider == "anthropic":
            async for chunk in self._astream_anthropic(messages, tools):
                yield chunk
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    async def _astream_mock(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Any] | None = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        A mock LLM stream generator for offline testing and verification.
        Simulates structured thinking, tool calling, and text generation.
        """
        await asyncio.sleep(0.1)  # Simulate network latency
        
        # Check if there are any tool calls or responses in history
        last_message = messages[-1] if messages else None
        
        # Check user queries
        user_queries = [
            str(msg.get("content", "")).lower()
            for msg in messages
            if msg.get("role") == "user"
        ]
        has_weather_query = any("weather" in q for q in user_queries)
        has_add_query = any("add" in q for q in user_queries)
        
        # If the user asked an add query and the last message is NOT a tool response
        if has_add_query and last_message and last_message.get("role") != "tool":
            import re
            user_content = next(
                str(msg.get("content", ""))
                for msg in reversed(messages)
                if msg.get("role") == "user"
            )
            numbers = [int(s) for s in re.findall(r'\d+', user_content)]
            a = numbers[0] if len(numbers) > 0 else 0
            b = numbers[1] if len(numbers) > 1 else 0
            
            yield LLMThoughtChunk(thought="Evaluating math query...")
            await asyncio.sleep(0.05)
            yield LLMThoughtChunk(thought=f"I need to call the add tool with parameters a={a} and b={b}")
            await asyncio.sleep(0.05)
            yield LLMToolCallChunk(name="add", arguments=json.dumps({"a": a, "b": b}), id="call_mock_add")

        # If the user asked a weather query and the last message is NOT a tool response
        elif has_weather_query and last_message and last_message.get("role") != "tool":
            # Stream a thought first
            yield LLMThoughtChunk(thought="Checking if get_weather tool is available...")
            await asyncio.sleep(0.05)
            yield LLMThoughtChunk(thought="I should invoke the get_weather tool for the location.")
            await asyncio.sleep(0.05)
            # Stream a tool call
            yield LLMToolCallChunk(name="get_weather", arguments='{"location": "San Francisco"}', id="call_mock_1")
            
        # If the last message IS a tool response, finalize the answer
        elif last_message and last_message.get("role") == "tool":
            tool_name = last_message.get("name", "tool")
            tool_content = last_message.get("content", "")
            yield LLMThoughtChunk(thought=f"Received tool response from {tool_name}: {tool_content}")
            await asyncio.sleep(0.05)
            yield LLMThoughtChunk(thought="Generating final summary based on tool details.")
            await asyncio.sleep(0.05)
            
            if tool_name == "get_weather":
                response_text = f"The weather in San Francisco is sunny and 72°F (based on tool result: {tool_content})."
            else:
                response_text = f"Result of {tool_name} is {tool_content}."
                
            for word in response_text.split(" "):
                yield LLMTokenChunk(token=word + " ")
                await asyncio.sleep(0.02)

                
        else:
            # Default normal response
            yield LLMThoughtChunk(thought="Standard question received. No tool needed.")
            await asyncio.sleep(0.05)
            
            response_text = "Hello! This is a response from the Tank framework Mock LLM provider."
            for word in response_text.split(" "):
                yield LLMTokenChunk(token=word + " ")
                await asyncio.sleep(0.02)


    async def _astream_openai(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Any] | None = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Stream from OpenAI API using official client.
        """
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)

        # Convert Tank messages format to OpenAI format
        openai_messages = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id"),
                    "name": msg.get("name"),
                    "content": str(msg.get("content"))
                })
            elif role == "assistant":
                formatted_assistant = {"role": "assistant"}
                if "content" in msg and msg["content"] is not None:
                    formatted_assistant["content"] = msg["content"]
                if "tool_calls" in msg:
                    formatted_assistant["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else tc["arguments"]
                            }
                        } for tc in msg["tool_calls"]
                    ]
                openai_messages.append(formatted_assistant)
            else:
                openai_messages.append({
                    "role": role,
                    "content": msg.get("content")
                })

        # Process tools list
        openai_tools = None
        if tools:
            openai_tools = [t.to_json_schema(provider="openai") for t in tools]

        stream = await client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            tools=openai_tools,
            stream=True,
            **self.kwargs
        )

        tool_calls_buffer = {}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Extract reasoning/thoughts if supported by model (e.g. o1/o3-mini)
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                yield LLMThoughtChunk(thought=delta.reasoning_content)

            # Stream normal tokens
            if delta.content:
                yield LLMTokenChunk(token=delta.content)

            # Handle streaming tool calls
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": []}
                    
                    if tc_delta.id:
                        tool_calls_buffer[idx]["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        tool_calls_buffer[idx]["name"] = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        tool_calls_buffer[idx]["arguments"].append(tc_delta.function.arguments)
                        # Yield tool calls dynamically as arguments stream in
                        yield LLMToolCallChunk(
                            name=tool_calls_buffer[idx]["name"],
                            arguments=tc_delta.function.arguments,
                            id=tool_calls_buffer[idx]["id"]
                        )

    async def _astream_anthropic(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Any] | None = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Stream from Anthropic API using official client.
        """
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=self.api_key)

        # Convert Tank messages to Anthropic messages format
        # Anthropic has strict message interleaving rules (User / Assistant / User...)
        # And system messages are passed in a top-level field.
        system_msg = ""
        anthropic_messages = []
        
        for msg in messages:
            role = msg.get("role")
            if role == "system":
                system_msg = msg.get("content", "")
            elif role == "tool":
                # In Anthropic, tool responses are sent as a 'user' message containing block of type 'tool_result'
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": str(msg.get("content"))
                    }]
                })
            elif role == "assistant":
                content_blocks = []
                if "content" in msg and msg["content"]:
                    content_blocks.append({"type": "text", "text": msg["content"]})
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["arguments"] if isinstance(tc["arguments"], dict) else json.loads(tc["arguments"])
                        })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            else:
                anthropic_messages.append({
                    "role": "user",
                    "content": msg.get("content")
                })

        anthropic_tools = None
        if tools:
            anthropic_tools = [t.to_json_schema(provider="anthropic") for t in tools]

        # Call Anthropic API
        stream_kwargs = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": 4096,
        }
        if system_msg:
            stream_kwargs["system"] = system_msg
        if anthropic_tools:
            stream_kwargs["tools"] = anthropic_tools

        async with client.messages.stream(**stream_kwargs) as stream:
            async for event in stream:
                # Handle text tokens
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield LLMTokenChunk(token=event.delta.text)
                
                # Handle thinking block (if available in models like Claude 3.7 Sonnet)
                elif event.type == "content_block_delta" and event.delta.type == "thinking_delta":
                    yield LLMThoughtChunk(thought=event.delta.thinking)
                    
                # Handle tool invocation starting
                elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                    # We will accumulate arguments in the block delta
                    pass
                elif event.type == "content_block_delta" and event.delta.type == "input_json_delta":
                    # Stream the arguments delta
                    # Get the current active content block
                    current_block = await stream.get_current_content_block()
                    if current_block and current_block.type == "tool_use":
                        yield LLMToolCallChunk(
                            name=current_block.name,
                            arguments=event.delta.partial_json,
                            id=current_block.id
                        )
