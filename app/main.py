"""FastAPI demo API for the observability lab.

Endpoints produce reproducible 200/400/404/500 responses and a bounded-slow
response so students can watch metrics, logs and (in Part 2) traces react.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app.logging_config import RequestLoggingMiddleware, configure_logging
from app.metrics import PrometheusMiddleware, metrics_endpoint, set_api_up
from app.otel import setup_otel

logger = logging.getLogger("obs-lab-api")

# In-memory catalogue of fake products.
PRODUCTS: dict[int, dict] = {
    1: {"id": 1, "name": "Teclado mecánico", "price": 79.9, "stock": 42},
    2: {"id": 2, "name": "Mouse inalámbrico", "price": 29.5, "stock": 130},
    3: {"id": 3, "name": "Monitor 27''", "price": 219.0, "stock": 18},
    4: {"id": 4, "name": "Auriculares USB-C", "price": 49.0, "stock": 76},
}

# Upper bound (seconds) for the artificial-slow endpoint, to protect the instance.
MAX_SLOW_SECONDS = 5.0

# Base URL of the downstream service (service-b) reached over the internal network.
# The httpx auto-instrumentation injects the W3C traceparent header on this call,
# so service-b continues the same trace (parent-child spans across both services).
SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service-b:8001")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    set_api_up()
    logger.info("api_startup", extra={"event": "startup"})
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Obs Lab API",
        version="1.0.0",
        description="API de demostración para el laboratorio de observabilidad.",
        lifespan=lifespan,
    )

    # Order matters: logging wraps metrics so both see the final status.
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    # OTel setup is gated by OTEL_ENABLED and is a no-op when disabled.
    setup_otel(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/")
    async def root() -> dict:
        return {
            "service": "obs-lab-api",
            "version": "1.0.0",
            "description": "API de demostración para métricas, logs y trazas.",
            "endpoints": [
                "/health", "/", "/products", "/products/{id}",
                "/simulate-error", "/simulate-slow", "/checkout", "/metrics",
            ],
        }

    @app.get("/products")
    async def list_products() -> dict:
        return {"products": list(PRODUCTS.values()), "count": len(PRODUCTS)}

    @app.get("/products/{product_id}")
    async def get_product(product_id: int) -> dict:
        product = PRODUCTS.get(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return product

    @app.get("/simulate-error")
    async def simulate_error(mode: str = Query("server")) -> JSONResponse:
        """Controlled error generator.

        mode=server (default) -> 500; mode=client -> an explicit 400.
        Any other value is treated as a bad query param and returns 400.
        """
        if mode == "server":
            raise HTTPException(status_code=500, detail="Error interno simulado")
        if mode == "client":
            return JSONResponse(status_code=400, content={"detail": "Error de cliente simulado"})
        raise HTTPException(status_code=400, detail=f"mode inválido: {mode!r}")

    @app.get("/simulate-slow")
    async def simulate_slow(
        seconds: float = Query(0.5, ge=0.0, le=MAX_SLOW_SECONDS)
    ) -> dict:
        """Sleep for a capped number of seconds (default 0.5, max MAX_SLOW_SECONDS)."""
        await asyncio.sleep(seconds)
        return {"slept_seconds": seconds, "max_seconds": MAX_SLOW_SECONDS}

    @app.get("/checkout")
    async def checkout(slow: int = Query(0, ge=0, le=1)) -> dict:
        """Cross-service endpoint that calls service-b over HTTP.

        A single request flows Client -> api -> service-b. The httpx call is
        already auto-instrumented and injects the W3C traceparent header, so the
        downstream span becomes a child of this request's span in the same trace
        (visible as one trace_id in Jaeger). ?slow=1 routes to service-b's
        slow-process path to surface the added latency as a longer child span.
        No manual span is added here to avoid duplicating the auto httpx span.
        """
        downstream_path = "/slow-process" if slow else "/process"
        url = f"{SERVICE_B_URL}{downstream_path}"
        async with httpx.AsyncClient(timeout=MAX_SLOW_SECONDS + 5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            downstream = response.json()
        return {
            "service": "obs-lab-api",
            "operation": "checkout",
            "downstream": downstream,
        }

    # prometheus-client scrape endpoint.
    app.add_route("/metrics", metrics_endpoint)

    return app


app = create_app()
