---
name: python-type-safety
description: Enforce strict type annotations and Pydantic validation patterns in Tank. Activate when writing new functions, adding parameters, defining models, working with tool schemas, or when type hints are missing or incorrect.
license: MIT
---

# Python Type Safety Guidelines for Tank

## Core Principle

Tank is a fully-typed Python framework. **Every** function signature, class attribute, and return value must carry explicit type annotations. The codebase requires Python ≥ 3.10 — use modern union syntax where applicable.

---

## Type Annotation Rules

### Function Signatures — Always Annotate Everything

```python
# ✅ Correct: full annotation including return type
async def run(self, query: str, session_id: str = "default") -> AsyncGenerator[AgentStep, None]:
    ...

# ❌ Wrong: missing return type and parameter types
async def run(self, query, session_id="default"):
    ...
```

### Python 3.10+ Union Syntax

Use `X | Y` instead of `Union[X, Y]` for new code:

```python
# ✅ Modern (preferred for new code)
def __init__(self, llm: LLM | None = None, tools: list[Tool] | None = None):

# Acceptable in existing code using typing module
from typing import Optional
def __init__(self, llm: Optional[LLM] = None):
```

### Collection Types — Use Lowercase (Python 3.9+)

```python
# ✅
fields: dict[str, Any] = {}
tools: list[Tool] = []
param_descriptions: dict[str, str] = {}

# ❌ (only needed for Python < 3.9)
from typing import Dict, List
fields: Dict[str, Any] = {}
```

---

## Pydantic Model Patterns

### Step Models — Always Inherit `BaseModel`

All agent step types must be `BaseModel` subclasses for serialization safety:

```python
class ThoughtStep(BaseModel):
    thought: str

class ToolCallStep(BaseModel):
    name: str
    arguments: dict[str, Any]
    id: str

class ToolResponseStep(BaseModel):
    name: str
    result: Any   # Any is acceptable — tool output is arbitrary
    id: str
```

### Dynamic Model Creation with `Field` Descriptions

When building Pydantic models from function signatures (as in `Tool`), inject `Field` with `description` when the docstring provides one:

```python
# ✅ With description from docstring
fields[param_name] = (param_type, Field(default=..., description=pdesc))

# ✅ Without description
fields[param_name] = (param_type, ...)

# ❌ Missing Field when description is available
fields[param_name] = (param_type, ...)  # loses the schema description
```

### Validating Tool Arguments

Always validate through the Pydantic model before calling the underlying function:

```python
async def __call__(self, *args, **kwargs) -> Any:
    sig = inspect.signature(self.func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()
    validated = self.args_model(**bound.arguments)  # raises ValidationError on bad input
    if inspect.iscoroutinefunction(self.func):
        return await self.func(**validated.model_dump())
    return self.func(**validated.model_dump())
```

---

## Type Aliases and Union Types

Define `Union` type aliases at module level for readability:

```python
# ✅ Define once, reuse everywhere
AgentStep = Union[ThoughtStep, ToolCallStep, ToolResponseStep, TextTokenStep, FinalResponseStep]
LLMStreamChunk = Union[LLMTokenChunk, LLMThoughtChunk, LLMToolCallChunk]

# ❌ Inline anonymous unions in every function signature
async def run(self, ...) -> AsyncGenerator[Union[ThoughtStep, ToolCallStep, ...], None]:
```

---

## `Any` Usage Policy

`Any` is a type safety escape hatch. Use it sparingly:

| Acceptable | Unacceptable |
|---|---|
| `result: Any` — tool results are legitimately arbitrary | Function parameters typed as `Any` |
| `fields: dict[str, Any]` — Pydantic field tuples mix types | Class attributes typed as `Any` |
| `**kwargs` on public adapters | Return type `-> Any` on non-trivial functions |

---

## Generic Return Types for Streaming

All streaming functions must declare `AsyncGenerator` return types explicitly:

```python
from typing import AsyncGenerator

async def astream(
    self,
    messages: list[dict[str, Any]],
    tools: list[Any] | None = None
) -> AsyncGenerator[LLMStreamChunk, None]:
    ...
```

---

## Type Narrowing with `isinstance`

Use `isinstance` for type narrowing — never string comparisons on type names:

```python
# ✅ isinstance narrows the type for static analysis
async for chunk in llm_stream:
    if isinstance(chunk, LLMThoughtChunk):
        yield ThoughtStep(thought=chunk.thought)
    elif isinstance(chunk, LLMTokenChunk):
        yield TextTokenStep(token=chunk.token)

# ❌ Bypasses static type analysis
if type(chunk).__name__ == "LLMThoughtChunk":
    ...
```

---

## `TypeVar` for Generic Decorators

When writing decorators that preserve the decorated class type (e.g. `agent_route`):

```python
from typing import TypeVar, Type

T = TypeVar("T", bound=Type[Agent])

def agent_route(self, path: str) -> Callable[[T], T]:
    def decorator(agent_cls: T) -> T:
        handler = create_agent_route_handler(agent_cls)
        self.starlette_app.add_route(path, handler)
        return agent_cls
    return decorator
```

---

## Checklist Before Submitting Code

- [ ] All function parameters and return types annotated
- [ ] No bare `except Exception: pass` clauses
- [ ] Pydantic models used for all structured data (steps, arguments)
- [ ] `create_model` calls include `Field(description=...)` when docstrings exist
- [ ] `Any` usage justified with an inline comment if non-obvious
- [ ] Type aliases defined at module level, not inline
