"""Prometheus instrumentation for the lab API.

All labels use the NORMALIZED route template (e.g. "/products/{id}"), never the raw
dynamic path, to avoid high-cardinality series. No user ids, IPs or request ids are
ever used as labels.
"""
from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

# Total requests, labelled by method, normalized route and HTTP status code.
REQUESTS_TOTAL = Counter(
    "api_requests_total",
    "Total HTTP requests processed by the API.",
    ["method", "route", "status"],
)

# Requests grouped by status class (2xx/4xx/5xx) for quick error-rate math.
REQUESTS_BY_CLASS = Counter(
    "api_requests_by_status_class_total",
    "Total HTTP requests grouped by status class.",
    ["method", "route", "status_class"],
)

# Latency histogram with buckets that let histogram_quantile compute p50/p90/p99.
REQUEST_LATENCY = Histogram(
    "api_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# API liveness gauge (1 = up). Set once at startup.
API_UP = Gauge("api_up", "API process liveness (1 = up).")


def set_api_up() -> None:
    API_UP.set(1)


def _route_template(request: Request) -> str:
    """Resolve the matched route template, falling back safely.

    Using request.scope["route"].path keeps labels on the template string
    ("/products/{id}") instead of the concrete path ("/products/42").
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    # No matched route (e.g. 404 for an unknown path): bucket under a constant
    # label to avoid unbounded cardinality from arbitrary URLs.
    return "__unmatched__"


class PrometheusMiddleware:
    """ASGI middleware recording request counts and latency per normalized route."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        method = request.method
        start = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        # Skip self-observation of the scrape endpoint to reduce noise.
        if request.url.path == "/metrics":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = _route_template(request)
            duration = time.perf_counter() - start
            status = status_holder["code"]
            status_class = f"{status // 100}xx"
            REQUESTS_TOTAL.labels(method, route, str(status)).inc()
            REQUESTS_BY_CLASS.labels(method, route, status_class).inc()
            REQUEST_LATENCY.labels(method, route).observe(duration)


def metrics_endpoint(_request: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
