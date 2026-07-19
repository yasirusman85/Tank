"""
Middleware components for Tank web framework.
Provides APIKeyMiddleware, RateLimiterMiddleware, and CostTracker.
"""
import time
from collections import defaultdict
from typing import Set, Optional, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce API key authentication on requests.
    Checks 'X-API-Key' or 'Authorization: Bearer <key>' headers.
    """
    def __init__(self, app, valid_keys: Set[str], exclude_paths: Optional[Set[str]] = None):
        super().__init__(app)
        self.valid_keys = valid_keys
        self.exclude_paths = exclude_paths or {"/", "/tank-admin", "/health"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        if not api_key:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:].strip()

        if not api_key or api_key not in self.valid_keys:
            return JSONResponse(
                {"error": "Unauthorized", "message": "Invalid or missing API key."},
                status_code=401
            )

        return await call_next(request)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter middleware per client IP.
    Returns HTTP 429 Too Many Requests if request count exceeds max_requests within window_seconds.
    """
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests_log = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()

        # Clean old timestamps
        cutoff = now - self.window_seconds
        self.requests_log[client_ip] = [t for t in self.requests_log[client_ip] if t > cutoff]

        if len(self.requests_log[client_ip]) >= self.max_requests:
            return JSONResponse(
                {
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded ({self.max_requests} requests per {self.window_seconds}s).",
                    "retry_after_seconds": round(self.window_seconds - (now - self.requests_log[client_ip][0]), 1)
                },
                status_code=429
            )

        self.requests_log[client_ip].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(self.max_requests - len(self.requests_log[client_ip]))
        return response


class CostTracker:
    """
    Utility for estimating token counts and pricing for popular models.
    """
    # Estimated pricing per 1K tokens (input/output average) in USD
    MODEL_PRICING = {
        "gpt-4o": 0.005,
        "gpt-4o-mini": 0.0003,
        "gpt-4-turbo": 0.01,
        "claude-3-5-sonnet-20241022": 0.003,
        "claude-3-haiku-20240307": 0.00025,
        "mock": 0.0
    }

    @classmethod
    def estimate_cost(cls, model_name: str, token_count: int) -> float:
        rate = cls.MODEL_PRICING.get(model_name.lower(), 0.002)
        return round((token_count / 1000.0) * rate, 6)
