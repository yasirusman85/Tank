import json
from starlette.testclient import TestClient

from tank import Tank, Agent, tool, LLM

# Setup a test Tank app
app = Tank()

@tool
def add(a: int, b: int) -> int:
    return a + b

@app.agent_route("/chat")
class RouteCalculatorAgent(Agent):
    llm = LLM(provider="mock")
    tools = [add]

def test_route_registration():
    """
    Ensure the agent_route decorator successfully registers the route on Starlette.
    """
    routes = [r.path for r in app.routes]
    assert "/chat" in routes

def test_agent_stream_response():
    """
    Verify that hitting the /chat route returns the correct SSE event sequences
    for the tool calling and response flow.
    """
    client = TestClient(app)
    
    payload = {"prompt": "Please add 5 and 7", "session_id": "test-session-123"}
    headers = {"x-session-id": "test-session-123"}
    
    events = []
    with client.stream("POST", "/chat", json=payload, headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        
        current_event = None
        for line in response.iter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line.replace("event:", "").strip()
            elif line.startswith("data:"):
                data_str = line.replace("data:", "").strip()
                data = json.loads(data_str)
                events.append((current_event, data))

    # Verify that the correct sequence of SSE events was streamed
    event_types = [e[0] for e in events]
    assert "thought" in event_types
    assert "tool_call" in event_types
    assert "tool_response" in event_types
    assert "token" in event_types
    assert "done" in event_types

    # Validate specific details of the tool call
    tool_calls = [e[1] for e in events if e[0] == "tool_call"]
    assert len(tool_calls) > 0
    assert tool_calls[0]["name"] == "add"
    assert tool_calls[0]["arguments"] == {"a": 5, "b": 7}

    # Validate specific details of the tool response
    tool_responses = [e[1] for e in events if e[0] == "tool_response"]
    assert len(tool_responses) > 0
    assert tool_responses[0]["name"] == "add"
    assert tool_responses[0]["result"] == 12

def test_different_query_parameter_formats():
    """
    Verify that query parameters are successfully extracted when no body is provided.
    """
    client = TestClient(app)
    
    with client.stream("POST", "/chat?prompt=add 10 and 20&session_id=session-99") as response:
        assert response.status_code == 200
        events = []
        for line in response.iter_lines():
            line = line.strip()
            if line.startswith("data:"):
                events.append(json.loads(line.replace("data:", "").strip()))
                
        # Find the tool call arguments
        tool_call_args = next(e["arguments"] for e in events if "arguments" in e and "name" in e and e["name"] == "add")
        assert tool_call_args == {"a": 10, "b": 20}
