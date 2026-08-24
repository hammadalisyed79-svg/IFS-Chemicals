"""API middleware — tenant, rate limit, request/trace IDs."""

from __future__ import annotations

import time
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from application.config import config
from application.tenant import set_scope, clear_scope
from infrastructure.observability.prometheus import inc, observe
from infrastructure.observability.tracing import get_request_id, get_trace_id, new_trace_id, set_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID") or set_request_id()
        trace = request.headers.get("X-Trace-ID") or new_trace_id()
        company_id = int(request.headers.get("X-Company-ID", "1") or 1)
        branch_id = int(request.headers.get("X-Branch-ID", "1") or 1)
        set_scope(company_id=company_id, branch_id=branch_id, enforce=True)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            response.headers["X-Trace-ID"] = trace
            ms = (time.perf_counter() - t0) * 1000
            observe("http_request_duration_ms", ms, {"path": request.url.path[:50]})
            inc("http_requests_total", labels={"method": request.method, "status": str(response.status_code)})
            return response
        finally:
            clear_scope()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{datetime.now().strftime('%Y%m%d%H%M')}"
        limit = int(config.get("api", "rate_limit_per_minute", "120") or 120)
        from database import get_connection
        with get_connection() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_api_rate_limits'").fetchone():
                return await call_next(request)
            row = conn.execute(
                "SELECT request_count FROM erp_api_rate_limits WHERE client_key=? AND window_start=?",
                (key, datetime.now().strftime("%Y-%m-%d %H:%M")),
            ).fetchone()
            count = (row[0] if row else 0) + 1
            if count > limit:
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
            conn.execute(
                """INSERT INTO erp_api_rate_limits(client_key,window_start,request_count)
                   VALUES(?,?,1)
                   ON CONFLICT(client_key,window_start) DO UPDATE SET request_count=?""",
                (key, datetime.now().strftime("%Y-%m-%d %H:%M"), count),
            )
        return await call_next(request)
