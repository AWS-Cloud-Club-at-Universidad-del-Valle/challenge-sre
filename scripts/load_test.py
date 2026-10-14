#!/usr/bin/env python3
"""Controlled traffic generator for the observability lab.

Produces a mix of successful, 404, 500, 400 and slow requests against the API so
students can watch the dashboards react. Rate-limited with safe defaults suitable
for a t3.small instance.

Usage:
    python scripts/load_test.py --duration 60 --rate 3 --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import os
import random
import time

import httpx

# (method, path) weighted request mix. Weights bias toward success but keep a
# steady trickle of errors and slow calls so every panel shows activity.
REQUEST_MIX = [
    ("/", 25),
    ("/health", 10),
    ("/products", 25),
    ("/products/1", 10),
    ("/products/999", 8),          # 404 (missing product)
    ("/simulate-error", 7),         # 500
    ("/simulate-error?mode=client", 5),  # 400
    ("/simulate-error?mode=bogus", 3),   # 400 (bad query)
    ("/simulate-slow?seconds=0.3", 7),   # bounded slow
]


def pick_path() -> str:
    paths, weights = zip(*REQUEST_MIX)
    return random.choices(paths, weights=weights, k=1)[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lab traffic generator.")
    parser.add_argument(
        "--duration", type=int,
        default=int(os.getenv("LOAD_TEST_DURATION", "60")),
        help="Total run time in seconds (default 60).",
    )
    parser.add_argument(
        "--rate", type=float,
        default=float(os.getenv("LOAD_TEST_RATE", "3")),
        help="Approximate requests per second (default 3).",
    )
    parser.add_argument(
        "--base-url", default=os.getenv("BASE_URL", "http://localhost:8000"),
        help="API base URL (default http://localhost:8000).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.rate <= 0:
        raise SystemExit("--rate must be positive")
    interval = 1.0 / args.rate
    deadline = time.time() + args.duration
    sent = 0
    counts: dict[int, int] = {}

    print(
        f"Generando tráfico contra {args.base_url} durante {args.duration}s "
        f"a ~{args.rate} req/s (Ctrl+C para detener)..."
    )
    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        try:
            while time.time() < deadline:
                path = pick_path()
                try:
                    resp = client.get(path)
                    counts[resp.status_code] = counts.get(resp.status_code, 0) + 1
                except httpx.HTTPError as exc:
                    print(f"  error de red en {path}: {exc}")
                sent += 1
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nInterrumpido por el usuario.")

    print(f"\nSolicitudes enviadas: {sent}")
    for code in sorted(counts):
        print(f"  HTTP {code}: {counts[code]}")


if __name__ == "__main__":
    main()
