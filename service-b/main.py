"""Downstream FastAPI microservice (service-b) for the distributed-tracing lab.

The api service calls this one over HTTP (GET /process and GET /slow-process).
Because the inbound request carries the W3C traceparent header that httpx
auto-instrumentation injected on the api side, the FastAPI auto-instrumentation
here continues the SAME trace: service-b spans become children of the api span,
so a single trace_id spans both services in Jaeger.

Only a single manual span is added, around a meaningful internal operation
(the simulated downstream "work"); the HTTP-handler span is already produced by
FastAPI auto-instrumentation, so we do not duplicate it.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Query
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.requests import Request
from starlette.responses import Response

from service_b.otel import get_tracer, setup_otel

logger = logging.getLogger("obs-lab-service-b")

# Upper bound (seconds) for the artificial-slow path, to protect the instance.
MAX_SLOW_SECONDS = 5.0


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(
        title="Obs Lab Service B",
        version="1.0.0",
        description="Servicio descendente para demostrar trazas distribuidas.",
    )

    # OTel setup is gated by OTEL_ENABLED and is a no-op when disabled.
    setup_otel(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/process")
    async def process() -> dict:
        """Normal downstream work: a short, bounded internal operation."""
        result = await _do_work(0.05)
        return {"service": "obs-lab-service-b", "operation": "process", **result}

    @app.get("/slow-process")
    async def slow_process(
        seconds: float = Query(1.0, ge=0.0, le=MAX_SLOW_SECONDS)
    ) -> dict:
        """Downstream work with extra bounded latency to demonstrate a bottleneck."""
        result = await _do_work(seconds)
        return {"service": "obs-lab-service-b", "operation": "slow-process", **result}

    @app.get("/metrics")
    async def metrics(_request: Request) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


async def _do_work(seconds: float) -> dict:
    """Simulate internal work inside a single manual span.

    This is the only manual span in service-b: it represents meaningful internal
    work and is NOT a duplicate of the FastAPI auto-instrumented request span.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("service-b.work") as span:
        span.set_attribute("work.sleep_seconds", seconds)
        await asyncio.sleep(seconds)
        return {"slept_seconds": seconds}


app = create_app()
