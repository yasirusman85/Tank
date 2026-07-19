"""
Main application class for Tank web framework.
Wraps Starlette ASGI app and provides decorators for agent and HTTP routes.
"""
from typing import Type, TypeVar, List, Optional, Callable, Any
from starlette.applications import Starlette

from tank.ai.agents import Agent
from tank.core.routing import (
    create_agent_route_handler,
    create_async_agent_route_handler,
    create_websocket_agent_route_handler,
    task_status_handler,
)

from tank.core.observability import admin_dashboard_handler


T = TypeVar("T", bound=Agent)

class Tank:
    """
    Tank wraps a Starlette ASGI application and provides decorators
    to bind URL endpoints to Agent classes and HTTP handlers.
    """
    def __init__(self, *args, **kwargs):
        self.starlette_app = Starlette(*args, **kwargs)
        # Register telemetry dashboard endpoint
        self.starlette_app.add_route("/tank-admin", admin_dashboard_handler, methods=["GET"])
        # Register async task status endpoint
        self.starlette_app.add_route("/tasks/{task_id}", task_status_handler, methods=["GET"])

    def agent_route(self, path: str, methods: Optional[List[str]] = None, name: Optional[str] = None):
        """
        Decorator to bind a URL endpoint directly to an Agent class.
        Defaults to POST requests.
        """
        if methods is None:
            methods = ["POST"]

        def decorator(agent_cls: Type[T]) -> Type[T]:
            handler = create_agent_route_handler(agent_cls)
            self.starlette_app.add_route(path, handler, methods=methods, name=name)
            return agent_cls
        return decorator

    def async_agent_route(self, path: str, methods: Optional[List[str]] = None, name: Optional[str] = None):
        """
        Decorator to bind an asynchronous background execution endpoint to an Agent class.
        Submits job to background TaskQueue and returns 202 Accepted with task_id.
        """
        if methods is None:
            methods = ["POST"]

        def decorator(agent_cls: Type[T]) -> Type[T]:
            handler = create_async_agent_route_handler(agent_cls)
            self.starlette_app.add_route(path, handler, methods=methods, name=name)
            return agent_cls
        return decorator

    def websocket_agent_route(self, path: str, name: Optional[str] = None):
        """
        Decorator to bind a WebSocket endpoint to an Agent class for bidirectional streaming.
        """
        def decorator(agent_cls: Type[T]) -> Type[T]:
            handler = create_websocket_agent_route_handler(agent_cls)
            self.add_websocket_route(path, handler, name=name)
            return agent_cls
        return decorator

    async def __call__(self, scope, receive, send):
        """
        ASGI entry point delegating to Starlette.
        """
        await self.starlette_app(scope, receive, send)

    # Delegation methods for standard Starlette features
    def route(self, path: str, methods: Optional[List[str]] = None, name: Optional[str] = None):
        """
        Decorator to register a standard URL route/endpoint.
        """
        def decorator(func: Callable) -> Callable:
            self.starlette_app.add_route(path, func, methods=methods, name=name)
            return func
        return decorator

    def add_route(self, path: str, route: Callable, methods: Optional[List[str]] = None, name: Optional[str] = None, **kwargs):
        self.starlette_app.add_route(path, route, methods=methods, name=name, **kwargs)

    def add_websocket_route(self, path: str, route: Callable, name: Optional[str] = None, **kwargs):
        from starlette.routing import WebSocketRoute
        self.starlette_app.routes.append(WebSocketRoute(path, endpoint=route, name=name))



    def add_middleware(self, middleware_class: Type, **kwargs):
        self.starlette_app.add_middleware(middleware_class, **kwargs)

    def exception_handler(self, exc_class_or_status_code):
        return self.starlette_app.exception_handler(exc_class_or_status_code)

    @property
    def state(self):
        return self.starlette_app.state

    @property
    def routes(self):
        return self.starlette_app.routes
