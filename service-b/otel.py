"""OpenTelemetry client wiring for the downstream service (service-b).

Mirrors app/otel.py: setup is gated by the OTEL_ENABLED env flag so the service
runs standalone when tracing is off. When enabled it exports OTLP spans to the
OTel Collector and auto-instruments FastAPI. service-b continues the trace that
the api started because the inbound request carries the W3C traceparent header
(FastAPIInstrumentor extracts it), so its spans become children of the api span.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("obs-lab-service-b.otel")

SERVICE_NAME = "obs-lab-service-b"

# Module-level tracer handle; populated by setup_otel() when tracing is enabled.
# Falls back to the global (no-op) tracer so get_tracer() is always safe to call.
_tracer = None


def _enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def setup_otel(app) -> bool:
    """Configure the OTel SDK and auto-instrument FastAPI.

    Returns True when tracing was enabled, False when it was a no-op.
    Safe to call when the collector is unreachable: export failures are handled
    by the SDK's batch processor and never crash the service.
    """
    global _tracer

    if not _enabled():
        logger.info("OTEL_ENABLED is not set to true; tracing disabled (no-op).")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
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

    _tracer = trace.get_tracer(SERVICE_NAME)
    logger.info("OpenTelemetry enabled; exporting spans to %s", endpoint)
    return True


def get_tracer():
    """Return the configured tracer, or the global (no-op) tracer when disabled."""
    if _tracer is not None:
        return _tracer
    from opentelemetry import trace

    return trace.get_tracer(SERVICE_NAME)
