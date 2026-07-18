from typing import Type, TypeVar, List, Optional
from starlette.applications import Starlette
from starlette.routing import BaseRoute

from tank.ai.agents import Agent
from tank.core.routing import create_agent_route_handler

T = TypeVar("T", bound=Type[Agent])

class Tank:
    """
    Tank wraps a Starlette ASGI application and provides a decorator
    to bind URL endpoints to Agent classes.
    """
    def __init__(self, *args, **kwargs):
        self.starlette_app = Starlette(*args, **kwargs)

    def agent_route(self, path: str, methods: Optional[List[str]] = None, name: Optional[str] = None):
        """
        Decorator to bind a URL endpoint directly to an Agent class.
        Defaults to POST requests.
        """
        if methods is None:
            methods = ["POST"]

        def decorator(agent_cls: T) -> T:
            handler = create_agent_route_handler(agent_cls)
            self.starlette_app.add_route(path, handler, methods=methods, name=name)
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
        from typing import Callable
        def decorator(func: Callable) -> Callable:
            self.starlette_app.add_route(path, func, methods=methods, name=name)
            return func
        return decorator

    def add_route(self, path: str, route: BaseRoute, **kwargs):
        self.starlette_app.add_route(path, route, **kwargs)


    def add_websocket_route(self, path: str, route: BaseRoute, **kwargs):
        self.starlette_app.add_websocket_route(path, route, **kwargs)

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
