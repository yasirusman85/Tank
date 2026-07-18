"""
Observability and telemetry tracer for Tank framework.
Logs agent runs, latency, step counts, and exposes the /tank-admin dashboard.
"""
import time
import datetime
from collections import deque
from typing import Dict, Any, List, Optional
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse


class TraceRecord:
    """Represents a single Agent execution run trace."""
    def __init__(self, trace_id: str, session_id: str, agent_name: str):
        self.trace_id = trace_id
        self.session_id = session_id
        self.agent_name = agent_name
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.latency_ms: Optional[float] = None
        self.status = "running"
        self.steps: List[Dict[str, Any]] = []

    def add_step(self, step_type: str, data: Dict[str, Any]):
        self.steps.append({
            "timestamp": time.time(),
            "type": step_type,
            "data": data
        })

    def finish(self, status: str = "completed"):
        self.end_time = time.time()
        self.latency_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "start_time": datetime.datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "latency_ms": self.latency_ms,
            "status": self.status,
            "step_count": len(self.steps),
            "steps": self.steps,
        }


class Tracer:
    """In-memory ring-buffer tracer store for Tank framework."""
    def __init__(self, maxlen: int = 100):
        self.traces: deque[TraceRecord] = deque(maxlen=maxlen)

    def record_trace(self, trace: TraceRecord):
        self.traces.appendleft(trace)

    def get_traces(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self.traces]

    def clear(self):
        self.traces.clear()


# Global tracer singleton
tracer = Tracer()


def admin_dashboard_handler(request: Request):
    """
    Renders the /tank-admin telemetry dashboard as HTML (or JSON if requested).
    """
    if "json" in request.query_params or request.headers.get("accept") == "application/json":
        return JSONResponse({
            "status": "healthy",
            "framework": "Tank",
            "total_runs": len(tracer.traces),
            "traces": tracer.get_traces()
        })

    traces = tracer.get_traces()
    rows_html = ""
    for t in traces:
        badge_color = "#10B981" if t["status"] == "completed" else ("#F59E0B" if t["status"] == "paused" else "#EF4444")
        rows_html += f"""
        <tr>
            <td style="padding:12px; border-bottom:1px solid #374151; font-family:monospace;">{t["trace_id"][:8]}</td>
            <td style="padding:12px; border-bottom:1px solid #374151;">{t["agent_name"]}</td>
            <td style="padding:12px; border-bottom:1px solid #374151; font-family:monospace;">{t["session_id"]}</td>
            <td style="padding:12px; border-bottom:1px solid #374151;">
                <span style="background:{badge_color}; color:#fff; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold;">
                    {t["status"].upper()}
                </span>
            </td>
            <td style="padding:12px; border-bottom:1px solid #374151;">{t["latency_ms"] or '-'} ms</td>
            <td style="padding:12px; border-bottom:1px solid #374151;">{t["step_count"]}</td>
            <td style="padding:12px; border-bottom:1px solid #374151; font-size:12px; color:#9CA3AF;">{t["start_time"]}</td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="7" style="padding:24px; text-align:center; color:#9CA3AF;">No agent execution traces recorded yet. Send a request to see telemetry live.</td></tr>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tank Telemetry Dashboard</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #111827; color: #F9FAFB; margin: 0; padding: 24px; }}
            .header {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #374151; padding-bottom: 16px; margin-bottom: 24px; }}
            .card {{ background: #1F2937; border-radius: 8px; border: 1px solid #374151; overflow: hidden; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th {{ background: #374151; padding: 12px; font-size: 12px; text-transform: uppercase; color: #9CA3AF; letter-spacing: 0.05em; }}
            .btn {{ background: #3B82F6; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; font-size: 14px; font-weight: 500; }}
            .btn:hover {{ background: #2563EB; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <h1 style="margin:0; font-size:24px; color:#60A5FA;">🛡️ Tank Dashboard</h1>
                <p style="margin:4px 0 0 0; color:#9CA3AF; font-size:14px;">Live Agent Telemetry & Run Tracing</p>
            </div>
            <a href="/tank-admin?json=true" class="btn" target="_blank">Export JSON</a>
        </div>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Trace ID</th>
                        <th>Agent</th>
                        <th>Session ID</th>
                        <th>Status</th>
                        <th>Latency</th>
                        <th>Steps</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html_content)
