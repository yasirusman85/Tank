"""
Unit tests for Tank observability tracer and /tank-admin telemetry endpoint.
"""
import pytest
from starlette.testclient import TestClient

from tank import Tank, Agent, LLM, tool
from tank.core.observability import tracer


@tool
def echo(text: str) -> str:
    return text


class TelemetryAgent(Agent):
    llm = LLM(provider="mock")
    tools = [echo]


def test_observability_tracing_and_admin_endpoint():
    tracer.clear()
    app = Tank()
    app.agent_route("/chat")(TelemetryAgent)

    client = TestClient(app)

    # 1. Trigger agent run
    with client.stream("POST", "/chat?prompt=weather") as response:
        assert response.status_code == 200

    # 2. Check tracer has recorded the run
    traces = tracer.get_traces()
    assert len(traces) == 1
    assert traces[0]["agent_name"] == "TelemetryAgent"
    assert traces[0]["status"] == "completed"
    assert traces[0]["latency_ms"] is not None

    # 3. Request /tank-admin JSON
    res = client.get("/tank-admin?json=true")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["total_runs"] == 1

    # 4. Request /tank-admin HTML
    res_html = client.get("/tank-admin")
    assert res_html.status_code == 200
    assert "Tank Dashboard" in res_html.text
    assert "TelemetryAgent" in res_html.text
