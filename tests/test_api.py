"""API tests covering the reproducible 200/400/404/500 and slow paths."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import MAX_SLOW_SECONDS, app

client = TestClient(app)


def test_root_ok():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "obs-lab-api"


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_products_ok():
    resp = client.get("/products")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["products"])
    assert body["count"] >= 1


def test_product_found():
    resp = client.get("/products/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_product_not_found_404():
    resp = client.get("/products/9999")
    assert resp.status_code == 404


def test_simulate_error_500():
    resp = client.get("/simulate-error")
    assert resp.status_code == 500


def test_simulate_error_client_400():
    resp = client.get("/simulate-error", params={"mode": "client"})
    assert resp.status_code == 400


def test_simulate_error_bad_query_400():
    resp = client.get("/simulate-error", params={"mode": "bogus"})
    assert resp.status_code == 400


def test_simulate_slow_within_bound():
    seconds = 0.3
    start = time.perf_counter()
    resp = client.get("/simulate-slow", params={"seconds": seconds})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert resp.json()["slept_seconds"] == seconds
    # Responds within the capped bound (plus generous overhead for CI).
    assert elapsed < MAX_SLOW_SECONDS + 2


def test_simulate_slow_rejects_over_cap_422():
    # Values above the cap are rejected by FastAPI validation (422).
    resp = client.get("/simulate-slow", params={"seconds": MAX_SLOW_SECONDS + 10})
    assert resp.status_code == 422


def test_metrics_endpoint_exposes_prometheus():
    client.get("/products")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "api_requests_total" in text
    assert "api_request_duration_seconds_bucket" in text
    assert "api_up" in text


def test_correlation_id_echoed():
    resp = client.get("/health", headers={"X-Correlation-ID": "test-corr-123"})
    assert resp.headers.get("X-Correlation-ID") == "test-corr-123"
