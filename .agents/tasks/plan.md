# Implementation Plan — AWS Observability Lab (metrics+logs + distributed tracing)

Greenfield repo at `/Users/juanhoyos/proyectos/challenge-sre`. Everything runs via Docker Compose on an internal network `obsnet`; the same compose runs on EC2 (t3.small, AL2023). Do NOT create AWS resources. Verified technical facts baked into this plan:

- Jaeger 1.60 all-in-one accepts OTLP natively on 4317/4318 but requires env `COLLECTOR_OTLP_ENABLED=true`. (Rephrased for compliance.)
- OTel Collector contrib 0.109 no longer ships the native Jaeger exporter; the correct wiring is the collector `otlp` exporter → Jaeger OTLP receiver. (Rephrased for compliance.)
- OTel Python SDK 1.27.0 pairs with contrib instrumentation 0.48b0 (same release train).
- Grafana 11.2 supports `tracesToLogsV2` on the Jaeger datasource and `derivedFields` (trace_id regex) on the Loki datasource via YAML provisioning.

Pinned versions: FastAPI 0.115, Uvicorn 0.32, prometheus-client 0.21, OTel SDK 1.27.0 + instrumentation 0.48b0, Prometheus v2.54, Loki 3.1, Grafana 11.2, Grafana Alloy 1.3, node_exporter 1.8, OTel Collector contrib 0.109, Jaeger 1.60, Amazon Linux 2023.

Directory layout:
```
app/                     FastAPI Part-1 API (+ OTel client, used in Part 2)
service-b/               FastAPI Part-2 downstream service
config/prometheus/       prometheus.yml
config/loki/             loki-config.yml
config/alloy/            config.alloy
config/otel/             otel-collector-config.yml
config/grafana/provisioning/datasources/  datasources.yml
config/grafana/provisioning/dashboards/    dashboards.yml (provider)
config/grafana/dashboards/                 infra.json, api.json
scripts/                 load_test.py
tests/                   test_api.py
docs/ (repo root *.md)   01-metricas-y-logs.md, 02-trazas-distribuidas-opentelemetry-jaeger.md, README.md
```

- [ ] 1. Create repo scaffolding and shared config files: `.gitignore` (ignore `.env`, `__pycache__`, `*.pyc`, loki/grafana data dirs), `.env.example` (GF_SECURITY_ADMIN_PASSWORD placeholder, LOAD_TEST_RATE/DURATION, OTEL_EXPORTER_OTLP_ENDPOINT), and `README.md` pointing to the two tutorials. No secrets committed.
      Files: `.gitignore`, `.env.example`, `README.md`
      Verify: files exist and `.env.example` contains no real secrets (visual check).

- [ ] 2. Build Part-1 FastAPI app in `app/`: endpoints `GET /health`, `GET /`, `GET /products`, `GET /products/{id}` (404 for missing), `GET /simulate-error` (controlled 500; 400 on bad query param), `GET /simulate-slow` (bounded latency via query, capped). Prometheus instrumentation with `prometheus-client`: counter total/per-normalized-route/per-status-class, histogram for latency (buckets enabling p50/p90/p99), `/metrics` endpoint, API-up gauge. Use route template as label (NOT raw dynamic path). Structured JSON logging to stdout (timestamp, severity, method, normalized route, status, duration, correlation id, error msg, trace_id — empty if no trace). OTel SDK/instrumentation wired (FastAPI + httpx auto-instrumentation, OTLP exporter to collector, controlled by env). Dockerfile + requirements.txt with pinned versions.
      Files: `app/main.py`, `app/metrics.py`, `app/logging_config.py`, `app/otel.py`, `app/requirements.txt`, `app/Dockerfile`
      Verify: `docker build app/` succeeds; `pytest tests/` (after item 8) passes; `curl localhost:8000/metrics` shows the metrics.

- [ ] 3. Build Part-2 `service-b/`: second FastAPI service with its own endpoints (e.g. `GET /process`, `GET /slow-process` injecting extra latency) and OTel instrumentation (FastAPI auto-instrumentation + OTLP export). Dockerfile + requirements.txt pinned.
      Files: `service-b/main.py`, `service-b/otel.py`, `service-b/requirements.txt`, `service-b/Dockerfile`
      Verify: `docker build service-b/` succeeds.

- [ ] 4. Wire `app` → `service-b` call: add an endpoint in `app` (e.g. `GET /checkout` or extend an existing flow) that makes an httpx call to `service-b` so Client→api→service-b produces parent-child spans via W3C traceparent propagation. Avoid duplicate manual spans for auto-instrumented ops; add manual spans only for meaningful internal work.
      Files: `app/main.py` (modify)
      Verify: after compose up, hit the endpoint and confirm a single trace_id with parent-child spans across both services in Jaeger UI.

- [ ] 5. Create telemetry backend configs: `config/prometheus/prometheus.yml` (scrape node_exporter, api, service-b, self), `config/loki/loki-config.yml` (single-binary, filesystem storage), `config/alloy/config.alloy` (discover api/service-b container logs, push to Loki), `config/otel/otel-collector-config.yml` (OTLP grpc/http receivers; memory_limiter + resource + batch processors; `otlp` exporter to Jaeger `jaeger:4317`; telemetry/logging).
      Files: `config/prometheus/prometheus.yml`, `config/loki/loki-config.yml`, `config/alloy/config.alloy`, `config/otel/otel-collector-config.yml`
      Verify: validated once compose runs (item 7): `promtool check config`, collector/loki/alloy start without config errors.

- [ ] 6. Create Grafana provisioning + dashboards: `datasources.yml` (Prometheus, Loki with `derivedFields` trace_id regex, Jaeger with `tracesToLogsV2`), dashboard provider `dashboards.yml`, and two dashboard JSONs — `infra.json` (CPU, mem used/avail, disk, network, exporter up, scrape health; titles/units/legends/refresh/descriptions; labeled as node_exporter OS metrics NOT CloudWatch) and `api.json` (total req, per endpoint, per status, 2xx/4xx/5xx, error rate, latency p50/p90/p99 via `histogram_quantile`, req/sec, API health).
      Files: `config/grafana/provisioning/datasources/datasources.yml`, `config/grafana/provisioning/dashboards/dashboards.yml`, `config/grafana/dashboards/infra.json`, `config/grafana/dashboards/api.json`
      Verify: Grafana starts, datasources show green, both dashboards auto-load.

- [ ] 7. Author `docker-compose.yml` wiring all services on internal network `obsnet`: api(8000), service-b, node_exporter(1.8), prometheus(9090), loki(3100), alloy, grafana(3000), otel-collector(4317/4318), jaeger(16686, env `COLLECTOR_OTLP_ENABLED=true`). Only grafana/api publish host ports as documented; the rest internal-only. Pin every image tag.
      Files: `docker-compose.yml`
      Verify: `docker compose config` is valid; `docker compose up -d` brings all services healthy; `docker compose ps` shows running.

- [ ] 8. Add unit tests in `tests/test_api.py` using pytest + FastAPI TestClient covering 200 (/, /products), 404 (missing product), 500 (/simulate-error), 400 (bad query), and /simulate-slow. Add `tests/requirements.txt` or reuse app deps. No tests beyond lab verification.
      Files: `tests/test_api.py`, `tests/__init__.py`
      Verify: `pytest tests/` passes.

- [ ] 9. Create `scripts/load_test.py`: mixed traffic (success, 404, 500, slow, cross-service) for a configurable duration/rate with safe defaults rate-limited for t3.small.
      Files: `scripts/load_test.py`
      Verify: run against local compose; Grafana API dashboard graphs change (manual observation).

- [ ] 10. Full local integration verification: `docker compose up -d`, run `scripts/load_test.py`, confirm Prometheus targets up, Grafana dashboards populated, logs queryable in Loki, and a distributed trace with parent-child spans across api/service-b visible in Jaeger, with trace_id correlation from Loki logs → Jaeger.
      Files: none (verification only)
      Verify: all four signals (metrics, logs, traces, correlation) observed; `docker compose down` cleans up.

- [ ] 11. Write `01-metricas-y-logs.md` (Spanish): objetivos; arquitectura + Mermaid; requisitos previos; AWS CLI perfil `stay` (account 550428926318, user JuanHoyos, us-east-1); creación EC2 t3.small AL2023 (justify t3.micro 1GB too small vs t3.small 2GB), SG least-privilege scoped to student IP (show `curl -s https://checkip.amazonaws.com`), IAM role `obs-lab-ec2-role`, tags Project=obs-lab, reuse key pair `ec2-docker-api-key`; Docker install; API; metrics instrumentation; node_exporter; Prometheus; Loki+Alloy; Grafana; both dashboards; traffic gen; verification; troubleshooting; security (ports/purpose/who); cost estimate (EC2/EBS/public IP/transfer; stopping EC2 doesn't remove EBS/IP cost; no NAT/ALB); cleanup. Clarify node_exporter OS metrics vs CloudWatch. Every step: qué/por qué/comando exacto/directorio/resultado esperado/cómo comprobar/qué revisar si falla. No fabricated outputs.
      Files: `01-metricas-y-logs.md`
      Verify: all required sections present in order; no `PEGA_AQUI_TU_IP` without acquisition command (grep check acceptable here as content check, plus manual review).

- [ ] 12. Write `02-trazas-distribuidas-opentelemetry-jaeger.md` (Spanish, builds on Part 1): objetivos; arquitectura trazas + Mermaid; métrica vs log vs traza; diseño del recorrido; implementación service-b + comparison table vs Lambda alternative (why B chosen); instrumentación OTel; propagación de contexto; OTel Collector config; despliegue Jaeger; config OTLP; peticiones de prueba; análisis de trazas/spans; simulación de latencia/errores; correlación logs/métricas/trazas; verificación; troubleshooting; seguridad y costes adicionales (~0 extra for container B); limpieza. Same per-step rigor. Exactly these two tutorials — no third doc.
      Files: `02-trazas-distribuidas-opentelemetry-jaeger.md`
      Verify: all required sections present in order; exactly two tutorial markdowns at repo root; manual review of accuracy.
