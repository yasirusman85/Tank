---
name: clean-code-architecture
description: Apply clean code and layered architecture principles when writing, reviewing, or refactoring Tank framework code. Activate when adding modules, restructuring packages, creating new classes, designing APIs, or when code feels messy or hard to follow.
license: MIT
---

# Clean Code & Architecture Guidelines for Tank

## Layered Architecture

Tank follows a strict three-layer architecture. Never skip layers or allow upward dependencies.

```
tank/
├── ai/          # Layer 1: Pure AI logic (agents, llm, tools, memory)
│   ├── agents.py   # Orchestration loop — depends only on llm, tools, memory
│   ├── llm.py      # Provider abstraction — no agent knowledge
│   ├── tools.py    # Tool registry and schema generation
│   └── memory.py   # Conversation history abstraction
├── core/        # Layer 2: Web/ASGI layer — depends on ai/, never vice versa
│   ├── app.py      # Tank app class, decorator registration
│   ├── routing.py  # Request parsing, agent instantiation
│   └── response.py # SSE streaming response
└── __init__.py  # Public surface — export only stable public API
```

**Rule**: `tank/ai/` must NEVER import from `tank/core/`. The AI layer is web-agnostic.

---

## Module Responsibilities (Single Responsibility)

Each module must do exactly one thing:

| Module | Owns | Must NOT |
|---|---|---|
| `agents.py` | Execution loop, step yielding, memory I/O | Know about HTTP, SSE, or providers |
| `llm.py` | Provider adapters, streaming normalization | Know about tool execution |
| `tools.py` | Schema gen, docstring parsing, validation | Execute agent logic |
| `routing.py` | Parse HTTP → extract prompt/session | Know about SSE format |
| `response.py` | Format steps → SSE bytes | Parse requests |

---

## Naming Conventions

```python
# Classes: PascalCase, descriptive noun
class AgentStreamResponse: ...   # ✅
class SSEResp: ...               # ❌ abbreviation, unclear

# Functions/methods: snake_case, verb-first
def parse_docstring_params(): ...  # ✅
def docstring(): ...               # ❌ not a verb

# Constants: UPPER_SNAKE_CASE
MAX_ITERATIONS = 5  # ✅

# Private helpers: single underscore prefix
def _astream_mock(): ...  # ✅

# Type aliases: PascalCase
AgentStep = Union[ThoughtStep, ToolCallStep, ...]  # ✅
```

---

## Class Design

- **Prefer class-level defaults + `__init__` overrides** (as in `Agent`):
  ```python
  class Agent:
      llm: LLM = LLM(provider="mock")   # class-level default
      tools: list[Tool] = []

      def __init__(self, llm=None, ...):
          if llm is not None:
              self.llm = llm
  ```
- **Never use mutable default arguments** — use `None` and override inside `__init__`.
- **Favor composition over inheritance**. Subclass only for well-defined extension points (e.g. `Agent`, `LLM`, `BaseMemory`).

---

## Function Design

- **Keep functions short**: a function body should fit in ~25 lines. Extract helpers if longer.
- **One level of abstraction per function**: don't mix high-level orchestration with low-level byte manipulation.
- **Avoid side effects** in parsing/transformation helpers (`parse_docstring_params` must be pure).
- **Async consistency**: if a function calls `await`, the entire call chain must be `async`. Never use `asyncio.run()` inside a framework function.

---

## Error Handling

```python
# ✅ Be specific, format errors for LLM self-correction
except ValueError as e:
    return f"Error: {str(e)} Please retry with correct inputs."

# ❌ Swallow exceptions silently
except Exception:
    pass

# ✅ Let Pydantic validation errors surface naturally via Tool.__call__
validated = self.args_model(**bound.arguments)  # raises ValidationError with full detail
```

---

## Documentation Standards

Every public class and function must have a docstring using Google style:

```python
def parse_docstring_params(doc: str) -> dict[str, str]:
    """
    Parses parameter descriptions from function docstrings.
    Supports both Google-style (Args:) and Sphinx-style (:param name:).

    Args:
        doc: The raw docstring to parse.

    Returns:
        A dict mapping parameter names to their description strings.
    """
```

- Parameters used in `@tool` functions **must** include Google/Sphinx-style docstrings — these are injected into the LLM's JSON Schema.
- Private helpers (`_astream_mock`) need only a one-line summary.

---

## Import Order

Follow PEP 8 import ordering, enforced in all files:

```python
# 1. Standard library
import json
import asyncio
from typing import List, Dict, Any, AsyncGenerator, Union

# 2. Third-party
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

# 3. First-party (relative within tank)
from tank.ai.agents import AgentStep, ThoughtStep
from tank.ai.tools import Tool
```

---

## Anti-Patterns to Avoid

| Anti-pattern | Fix |
|---|---|
| `from tank import *` in module files | Use explicit named imports |
| Hardcoding provider strings (`"openai"`) in multiple places | Define constants or an `Enum` |
| Logic inside `__init__.py` beyond imports | Keep `__init__.py` to re-exports only |
| `print()` for logging | Use `logging` module or surface as step events |
| Mixing sync and async code paths | Keep all I/O async end-to-end |
