# Changelog

All notable changes to the Tank framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-19

### Added
- **Core ASGI Engine**: Wraps Starlette with `@app.agent_route` and `@app.route` decorators.
- **SSE Streaming**: `AgentStreamResponse` for streaming typed agent execution steps over HTTP.
- **LLM Abstractions**: Unified provider interface supporting OpenAI, Anthropic, and zero-dependency Mock streaming.
- **Dynamic Tools**: `@tool` decorator with Google/Sphinx docstring parameter parsing and Pydantic argument validation.
- **Structured Outputs**: `response_model` support with automatic self-correction loops on schema mismatches.
- **Human-in-the-Loop (HITL)**: `@tool(requires_approval=True)` support with paused loop state and `agent.resume()` entrypoint.
- **Tiered Memory**: `SimpleMemory`, `SQLAlchemyMemory` (SQLite/PostgreSQL persistence), and `TokenBufferMemory`.
- **RAG Components**: `MockEmbeddings`, `OpenAIEmbeddings`, `SimpleVectorStore`, and `Retriever` tool builder.
- **Observability Dashboard**: Built-in `/tank-admin` route for tracking run latency, step counts, and active sessions.
- **CLI Utility**: `tank startproject`, `tank startagent`, and `tank runserver` commands.
