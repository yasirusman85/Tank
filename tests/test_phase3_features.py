"""
Comprehensive integration and unit test suite for Phase 3 feature expansion:
WebSockets, Multi-Agent Orchestration, Async Task Queue, Advanced RAG, Middleware, and CLI Tools.
"""
import pytest
import asyncio
from starlette.testclient import TestClient

from tank import (
    Tank,
    Agent,
    LLM,
    tool,
    SupervisorAgent,
    HandoffStep,
    RecursiveTextSplitter,
    SimpleReranker,
    MockEmbeddings,
    SimpleVectorStore,
    APIKeyMiddleware,
    RateLimiterMiddleware,
    CostTracker,
)


@tool
def add_tool(a: int, b: int) -> int:
    return a + b


class MathAgent(Agent):
    llm = LLM(provider="mock")
    tools = [add_tool]


# ----------------------------------------------------
# 1. Advanced RAG Tests
# ----------------------------------------------------
def test_recursive_text_splitter():
    splitter = RecursiveTextSplitter(chunk_size=50, chunk_overlap=10)
    text = "Tank is an AI-native web framework. It provides fast SSE streaming, tool calling, and RAG primitives for Python developers."
    chunks = splitter.split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= 60 for c in chunks)


@pytest.mark.asyncio
async def test_hybrid_search_and_reranker():
    embeddings = MockEmbeddings()
    store = SimpleVectorStore(embeddings)
    await store.add_texts([
        "Python web framework for streaming AI agents",
        "JavaScript frontend framework with React",
        "PostgreSQL database query optimization tips"
    ])

    results = await store.similarity_search("python framework", k=2, search_type="hybrid")
    assert len(results) == 2
    assert "Python" in results[0]["text"]

    reranker = SimpleReranker()
    reranked = await reranker.rerank("python framework", results, top_k=1)
    assert len(reranked) == 1
    assert "Python" in reranked[0]["text"]


# ----------------------------------------------------
# 2. Security & Rate Limiting Middleware Tests
# ----------------------------------------------------
def test_api_key_and_rate_limiter_middleware():
    app = Tank()
    app.add_middleware(APIKeyMiddleware, valid_keys={"secret-key-123"})
    app.agent_route("/chat")(MathAgent)

    client = TestClient(app)

    # 1. Unauthorized request
    res_unauth = client.post("/chat?prompt=add 5 and 5")
    assert res_unauth.status_code == 401

    # 2. Authorized request
    res_auth = client.post("/chat?prompt=add 5 and 5", headers={"X-API-Key": "secret-key-123"})
    assert res_auth.status_code == 200

    # 3. Cost Tracker calculation
    cost = CostTracker.estimate_cost("gpt-4o", 1000)
    assert cost == 0.005


# ----------------------------------------------------
# 3. Async Background Task Execution Tests
# ----------------------------------------------------
def test_async_agent_task_execution():
    app = Tank()
    app.async_agent_route("/async-chat")(MathAgent)

    client = TestClient(app)
    res = client.post("/async-chat?prompt=add 10 and 20")
    assert res.status_code == 202
    data = res.json()
    assert "task_id" in data
    assert data["status"] in ("pending", "running", "completed")

    task_id = data["task_id"]

    # Poll status
    res_status = client.get(f"/tasks/{task_id}")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["task_id"] == task_id


# ----------------------------------------------------
# 4. Multi-Agent Orchestration & Supervisor Tests
# ----------------------------------------------------
@pytest.mark.asyncio
async def test_supervisor_agent_handoff():
    math_agent = MathAgent()
    supervisor = SupervisorAgent(workers={"math": math_agent})

    steps = []
    async for step in supervisor.run("math query add 5 and 5"):
        steps.append(step)

    handoffs = [s for s in steps if isinstance(s, HandoffStep)]
    assert len(handoffs) == 1
    assert handoffs[0].target_agent == "math"


# ----------------------------------------------------
# 5. WebSocket Transport Tests
# ----------------------------------------------------
def test_websocket_agent_route():
    app = Tank()
    app.websocket_agent_route("/ws-chat")(MathAgent)

    client = TestClient(app)
    with client.websocket_connect("/ws-chat") as websocket:
        websocket.send_json({"type": "prompt", "prompt": "add 3 and 4", "session_id": "ws-1"})
        events = []
        try:
            for _ in range(5):
                frame = websocket.receive_json()
                events.append(frame.get("event"))
        except Exception:
            pass

        assert "thought" in events or "tool_call" in events
