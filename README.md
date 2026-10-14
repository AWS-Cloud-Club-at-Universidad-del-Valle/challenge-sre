# AWS Observability Lab — Métricas, Logs y Trazas

Laboratorio educativo de observabilidad: una API FastAPI instrumentada y un stack
de Docker Compose (Prometheus, Loki, Grafana Alloy, Grafana, node_exporter y, en la
Parte 2, OpenTelemetry Collector + Jaeger) pensado para correr en una sola instancia
EC2 `t3.small` (Amazon Linux 2023).

## Estructura

- `app/` — API FastAPI (Parte 1) instrumentada con Prometheus, logging JSON y cliente OTel.
- `config/` — configuración de Prometheus, Loki, Alloy y Grafana (datasources + dashboards).
- `scripts/load_test.py` — generador de tráfico controlado.
- `tests/` — pruebas con pytest + FastAPI TestClient.
- `docker-compose.yml` — stack completo sobre la red interna `obsnet`.

## Tutoriales

1. **Parte 1 — Métricas y logs:** `01-metricas-y-logs.md`
2. **Parte 2 — Trazas distribuidas (OpenTelemetry + Jaeger):** `02-trazas-distribuidas-opentelemetry-jaeger.md`

## Arranque rápido (local)

```bash
cp .env.example .env            # ajusta GF_SECURITY_ADMIN_PASSWORD
docker compose config           # valida
docker compose build
docker compose up -d
docker compose ps
```

- API: http://localhost:8000  (métricas en `/metrics`)
- Grafana: http://localhost:3000  (admin / el password de tu `.env`)

El resto de servicios son internos a la red `obsnet` y se consultan vía túnel SSH en EC2.

## Seguridad

No se versionan credenciales. Usa `.env` (ignorado por git) a partir de `.env.example`.
En EC2 las aplicaciones usan IAM roles; no se incrustan llaves en el repo ni en imágenes.
