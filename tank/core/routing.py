from typing import Type, Callable, Any
from starlette.requests import Request
from starlette.responses import Response

from tank.ai.agents import Agent
from tank.core.response import AgentStreamResponse

def create_agent_route_handler(agent_cls: Type[Agent]) -> Callable[[Request], Response]:
    """
    Creates a Starlette route handler for the given Agent class.
    Parses request payload (JSON/form/query params), session IDs, and headers,
    instantiates the agent, and returns an AgentStreamResponse.
    """
    async def route_handler(request: Request) -> Response:
        prompt = ""
        session_id = "default"

        # 1. Parse from Query parameters (GET or fallback)
        query_params = request.query_params
        if "prompt" in query_params:
            prompt = query_params["prompt"]
        elif "query" in query_params:
            prompt = query_params["query"]

        if "session_id" in query_params:
            session_id = query_params["session_id"]

        # 2. Parse from request body (POST/PUT/PATCH)
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.json()
                    if isinstance(body, dict):
                        prompt = body.get("prompt") or body.get("query") or prompt
                        session_id = body.get("session_id") or session_id
                except Exception:
                    pass
            elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                try:
                    form = await request.form()
                    prompt = form.get("prompt") or form.get("query") or prompt
                    session_id = form.get("session_id") or session_id
                except Exception:
                    pass

        # 3. Parse headers (e.g. custom session ID header)
        if "x-session-id" in request.headers:
            session_id = request.headers["x-session-id"]

        # Instantiate the Agent and attach request metadata
        agent = agent_cls()
        agent.request = request
        agent.headers = dict(request.headers)

        # Execute agent stream
        steps_generator = agent.run(query=prompt, session_id=session_id)

        # Return streaming response
        return AgentStreamResponse(steps_generator)

    return route_handler
