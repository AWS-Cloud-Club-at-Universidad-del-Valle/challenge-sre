"""OpenTelemetry client wiring for the lab API.

Guarded by the OTEL_ENABLED env flag so Part 1 runs standalone: when the flag is
not truthy (or the collector is absent) setup is a no-op and the app keeps working
without any OTLP export. Part 2 flips OTEL_ENABLED=true and points
OTEL_EXPORTER_OTLP_ENDPOINT at the collector.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("obs-lab-api.otel")

SERVICE_NAME = "obs-lab-api"


def _enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def setup_otel(app) -> bool:
    """Configure the OTel SDK and auto-instrument FastAPI + httpx.

    Returns True when tracing was enabled, False when it was a no-op.
    Safe to call when the collector is unreachable: export failures are handled
    by the SDK's batch processor and never crash the app.
    """
    if not _enabled():
        logger.info("OTEL_ENABLED is not set to true; tracing disabled (no-op).")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:  # pragma: no cover - only when optional deps missing
        logger.warning("OpenTelemetry packages not installed; tracing disabled.")
        return False

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    logger.info("OpenTelemetry enabled; exporting spans to %s", endpoint)
    return True


def current_trace_id() -> str:
    """Return the active trace id as a 32-char hex string, or "" when none.

    Importing opentelemetry here is cheap and works even when tracing is disabled
    (the default no-op tracer yields an all-zero invalid context).
    """
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover
        return ""

    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is None or not ctx.is_valid:
        return ""
    return format(ctx.trace_id, "032x")
