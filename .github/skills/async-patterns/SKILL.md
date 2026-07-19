---
name: async-patterns
description: Apply correct asyncio and async generator patterns in Tank. Activate when writing async functions, streaming responses, concurrent tool execution, LLM provider adapters, or when debugging event loop, await, or generator-related issues.
license: MIT
---

# Async & Streaming Patterns for Tank

## Core Model

Tank's execution pipeline is fully asynchronous and push-based. Every operation — LLM inference, tool execution, SSE formatting — is expressed as an `async for` chain from the LLM adapter to the HTTP response body.

```
HTTP Request
    │
    ▼
routing.py: create_agent_route_handler()
    │  await request.json()
    ▼
agents.py: Agent.run()           ← AsyncGenerator[AgentStep, None]
    │  async for chunk in llm.astream()
    │  await asyncio.gather(*tool_tasks)
    ▼
response.py: AgentStreamResponse
    │  async for step in steps_generator
    │  yield sse_message.encode("utf-8")
    ▼
HTTP Response (text/event-stream)
```

**Rule**: Never block the event loop. If you need to run synchronous I/O, use `asyncio.to_thread()`.

---

## AsyncGenerator Pattern

All streaming functions must use `yield` inside an `async def` and declare the return type explicitly:

```python
# ✅ Correct async generator
async def run(self, query: str, session_id: str = "default") -> AsyncGenerator[AgentStep, None]:
    messages = await self.memory.get_messages(session_id)
    async for chunk in self.llm.astream(messages):
        if isinstance(chunk, LLMThoughtChunk):
            yield ThoughtStep(thought=chunk.thought)

# ❌ Wrong: mixing sync return with async iteration
def run(self, query: str) -> list[AgentStep]:
    ...  # collects everything into memory — kills streaming
```

### Consuming AsyncGenerators

Always use `async for` — never `list()` or `next()` on an async generator in production paths:

```python
# ✅
steps = []
async for step in agent.run(query):
    steps.append(step)

# ❌ Blocks entire event loop
steps = list(agent.run(query))
```

---

## Concurrent Tool Execution with `asyncio.gather`

When the LLM requests multiple tool calls in one turn, run them concurrently:

```python
# ✅ Concurrent: total time ≈ max(individual times)
async def run_single_tool(tc_dict: dict) -> Any:
    tool_obj = self._tools_map.get(tc_dict["name"])
    if not tool_obj:
        return f"Error: Tool '{tc_dict['name']}' not registered. Please retry with correct inputs."
    try:
        return await tool_obj(**tc_dict["arguments"])
    except Exception as e:
        return f"Error: {str(e)} Please retry with correct inputs."

tasks = [run_single_tool(tc) for tc in tool_calls_to_run]
results = await asyncio.gather(*tasks)

# ❌ Sequential: total time = sum of all times
for tc in tool_calls_to_run:
    result = await run_single_tool(tc)
```

### `asyncio.gather` Error Handling

By default, `gather` propagates the first exception. For tool execution, always catch inside the coroutine (as above) so all results are returned regardless of individual failures.

---

## Mixing Sync and Async Tools

`Tool.__call__` supports both sync and async underlying functions transparently:

```python
# ✅ Correct pattern in Tool.__call__
if inspect.iscoroutinefunction(self.func):
    return await self.func(**validated.model_dump())
else:
    return self.func(**validated.model_dump())

# ✅ If the sync function does blocking I/O, wrap it
if inspect.iscoroutinefunction(self.func):
    return await self.func(**kwargs)
else:
    return await asyncio.to_thread(self.func, **kwargs)
```

---

## LLM Streaming Adapter Pattern

Each provider adapter (`_astream_openai`, `_astream_anthropic`, `_astream_mock`) must:
1. Be an `async def` generator (uses `yield`).
2. Normalize provider-specific events into `LLMStreamChunk` union types.
3. Never raise provider-specific exceptions to callers — wrap them.

```python
async def _astream_openai(
    self,
    messages: list[dict[str, Any]],
    tools: list[Any] | None = None
) -> AsyncGenerator[LLMStreamChunk, None]:
    client = AsyncOpenAI(api_key=self.api_key)
    stream = await client.chat.completions.create(
        model=self.model, messages=openai_messages, stream=True
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield LLMTokenChunk(token=delta.content)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                yield LLMToolCallChunk(name=..., arguments=..., id=...)
```

---

## SSE Streaming in `AgentStreamResponse`

The SSE iterator must be a nested `async def` generator inside `__init__`:

```python
class AgentStreamResponse(StreamingResponse):
    def __init__(self, steps_generator: AsyncGenerator[AgentStep, None], **kwargs):
        async def sse_iterator() -> AsyncGenerator[bytes, None]:
            async for step in steps_generator:
                if isinstance(step, ThoughtStep):
                    event, data = "thought", {"thought": step.thought}
                elif isinstance(step, FinalResponseStep):
                    event, data = "done", {"text": step.text}
                else:
                    continue
                yield f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")

        super().__init__(content=sse_iterator(), media_type="text/event-stream")
```

**Critical SSE headers** — always set these:
```python
headers["Cache-Control"] = "no-cache"
headers["Connection"] = "keep-alive"
headers["X-Accel-Buffering"] = "no"  # Disables nginx buffering
```

---

## Async Context Managers

When using the Anthropic streaming API, always use `async with`:

```python
# ✅
async with client.messages.stream(**stream_kwargs) as stream:
    async for event in stream:
        ...

# ❌ Don't call .stream() without a context manager — leaks connections
stream = client.messages.stream(**stream_kwargs)
```

---

## Testing Async Code

Use `pytest-asyncio` with `@pytest.mark.asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_parallel_tool_execution():
    agent = Agent(llm=MockLLM(), tools=[slow_tool_1, slow_tool_2])
    start = time.time()
    steps = [step async for step in agent.run("run tools")]
    assert time.time() - start < 0.5  # proves concurrency

# In pyproject.toml, configure strict mode:
# [tool.pytest.ini_options]
# asyncio_mode = "strict"
```

---

## Common Pitfalls

| Pitfall | Fix |
|---|---|
| `await` inside a sync function | Make the function `async def` |
| `asyncio.run()` inside an already-running event loop | Use `await` directly; never nest event loops |
| Forgetting `async for` when consuming a generator | Always use `async for`, not `for` |
| Blocking sleep `time.sleep()` inside async code | Use `await asyncio.sleep()` |
| Creating tasks without awaiting them | Store in a list and `await asyncio.gather(*tasks)` |
| Defining a nested `async def` that doesn't use `yield` | It's a coroutine, not a generator — remove `async` or add `yield` |
