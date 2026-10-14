"""Structured JSON logging to stdout for the lab API.

Each access log line is a single JSON object with: timestamp, severity, HTTP method,
normalized route, status code, request duration (ms), correlation id and trace_id
(from the active OTel span, empty string when there is no active trace). Secrets,
tokens and passwords are never logged.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from starlette.requests import Request

from app.metrics import _route_template
from app.otel import current_trace_id

CORRELATION_HEADER = "X-Correlation-ID"

access_logger = logging.getLogger("obs-lab-api.access")


class JSONFormatter(logging.Formatter):
    """Render log records as compact JSON. Extra fields come via record.__dict__."""

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the JSON formatter on the root handler (stdout only)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Silence uvicorn's default access logger; we emit our own structured line.
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False


class RequestLoggingMiddleware:
    """ASGI middleware emitting one structured JSON access log per request.

    Also generates/propagates the X-Correlation-ID header so a client-supplied id
    is reused and echoed back, and a fresh uuid4 is minted otherwise.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        # Do not emit an access log for the Prometheus scrape endpoint.
        if request.url.path == "/metrics":
            await self.app(scope, receive, send)
            return

        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        start = time.perf_counter()
        state = {"status": 500, "error": None}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append(
                    (CORRELATION_HEADER.encode("latin-1"), correlation_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001 - log then re-raise
            state["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            extra = {
                "method": request.method,
                "route": _route_template(request),
                "status": state["status"],
                "duration_ms": duration_ms,
                "correlation_id": correlation_id,
                "trace_id": current_trace_id(),
            }
            if state["error"]:
                extra["error"] = state["error"]
            level = logging.ERROR if state["status"] >= 500 else logging.INFO
            access_logger.log(level, "http_request", extra=extra)
