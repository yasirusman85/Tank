"""
Route handling factories for Tank agent endpoints.
Binds Agent classes to Starlette request handlers.
"""
from typing import Type, Callable
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

        # Tracing execution
        import uuid
        from tank.core.observability import tracer, TraceRecord

        trace_record = TraceRecord(
            trace_id=str(uuid.uuid4()),
            session_id=session_id,
            agent_name=agent_cls.__name__
        )

        async def traced_generator():
            try:
                async for step in agent.run(query=prompt, session_id=session_id):
                    step_type = step.__class__.__name__
                    step_data = step.model_dump() if hasattr(step, "model_dump") else {}
                    trace_record.add_step(step_type, step_data)
                    yield step
                trace_record.finish(status="completed")
            except Exception as e:
                trace_record.finish(status="failed")
                raise e
            finally:
                tracer.record_trace(trace_record)

        # Return streaming response
        return AgentStreamResponse(traced_generator())

    return route_handler


def create_async_agent_route_handler(agent_cls: Type[Agent]) -> Callable[[Request], Response]:
    """
    Creates a Starlette route handler that submits the agent execution to background task queue.
    """
    from starlette.responses import JSONResponse
    from tank.core.tasks import task_queue

    async def async_route_handler(request: Request) -> Response:
        prompt = ""
        session_id = "default"

        query_params = request.query_params
        if "prompt" in query_params:
            prompt = query_params["prompt"]
        elif "query" in query_params:
            prompt = query_params["query"]
        if "session_id" in query_params:
            session_id = query_params["session_id"]

        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.json()
                if isinstance(body, dict):
                    prompt = body.get("prompt") or body.get("query") or prompt
                    session_id = body.get("session_id") or session_id
            except Exception:
                pass

        agent = agent_cls()
        agent.request = request
        agent.headers = dict(request.headers)

        task_record = await task_queue.submit_task(agent, prompt, session_id)
        return JSONResponse(task_record.to_dict(), status_code=202)

    return async_route_handler


async def task_status_handler(request: Request) -> Response:
    """
    Starlette route handler to retrieve async task status by task_id parameter.
    """
    from starlette.responses import JSONResponse
    from tank.core.tasks import task_queue

    task_id = request.path_params.get("task_id") or request.query_params.get("task_id", "")
    task_record = task_queue.get_task(task_id)
    if not task_record:
        return JSONResponse({"error": "Not Found", "message": f"Task '{task_id}' not found."}, status_code=404)

    return JSONResponse(task_record.to_dict())


def create_websocket_agent_route_handler(agent_cls: Type[Agent]) -> Callable:
    """
    Creates a Starlette WebSocket handler for bidirectional agent communication.
    Supports streaming steps outbound and receiving client approval frames inbound.
    """
    from starlette.websockets import WebSocket
    from tank.core.response import AgentStepEventFactory

    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        agent = agent_cls()
        agent.request = websocket
        agent.headers = dict(websocket.headers)

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "prompt")

                if msg_type in ("prompt", "query"):
                    prompt = data.get("prompt") or data.get("query", "")
                    session_id = data.get("session_id", "default")
                    
                    async for step in agent.run(query=prompt, session_id=session_id):
                        event = AgentStepEventFactory.create(step)
                        if event:
                            await websocket.send_json({"event": event.name, "data": event.data})

                elif msg_type == "approval":
                    session_id = data.get("session_id", "default")
                    tool_call_id = data.get("tool_call_id", "")
                    approved = bool(data.get("approved", True))
                    feedback = data.get("feedback")

                    async for step in agent.resume(session_id, tool_call_id, approved, user_feedback=feedback):
                        event = AgentStepEventFactory.create(step)
                        if event:
                            await websocket.send_json({"event": event.name, "data": event.data})

        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    return websocket_endpoint


