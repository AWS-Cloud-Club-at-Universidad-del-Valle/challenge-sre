# AWS Observability Lab — Métricas, Logs y Trazas (desplegado con AWS CDK)

Laboratorio educativo de observabilidad: una API FastAPI instrumentada, un servicio
descendente `service-b` y un stack de Docker Compose (Prometheus, Loki, Grafana Alloy,
Grafana, node_exporter, OpenTelemetry Collector y Jaeger). Toda la infraestructura se
**aprovisiona en AWS con AWS CDK**: una sola ejecución (`cdk deploy`) crea una instancia
EC2 `t3.small` (Amazon Linux 2023) cuyo *user-data* instala Docker y arranca
automáticamente todos los servicios. El estudiante no monta nada a mano: despliega con CDK
y sigue los tutoriales para construir los dashboards y explorar las trazas.

## Estructura

- `cdk/` — app de **AWS CDK v2 (Python)** que crea la EC2 y arranca todo con Docker vía
  *user-data* (ver `cdk/README.md`).
- `app/` — API FastAPI (Parte 1) instrumentada con Prometheus, logging JSON y cliente OTel.
- `service-b/` — servicio descendente (Parte 2) para las trazas distribuidas.
- `config/` — configuración de Prometheus, Loki, Alloy, OTel Collector y Grafana.
- `scripts/load_test.py` — generador de tráfico controlado.
- `tests/` — pruebas con pytest + FastAPI TestClient.
- `docker-compose.yml` — stack completo sobre la red interna `obsnet`.

## Tutoriales (ruta principal: AWS CDK)

Sigue los tutoriales en orden. Despliegan la infraestructura con CDK y se concentran en
construir los dashboards y explorar las trazas.

1. **Parte 1 — Métricas y logs (despliegue con CDK + dashboards):**
   [`01-metricas-y-logs.md`](./01-metricas-y-logs.md)
2. **Parte 2 — Trazas distribuidas (OpenTelemetry + Jaeger):**
   [`02-trazas-distribuidas-opentelemetry-jaeger.md`](./02-trazas-distribuidas-opentelemetry-jaeger.md)

Flujo resumido (detalle en la Parte 1):

```bash
cd cdk
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap aws://550428926318/us-east-1 --profile stay
cdk deploy -c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32 --profile stay
# ... usa el lab ...
cdk destroy -c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32 --profile stay
```

Tras `cdk deploy`, abre Grafana en `http://<PublicIp>:3000` (output `GrafanaUrl`).

## Apéndice opcional: arranque local (offline)

Solo si quieres probar el stack **sin AWS** (no es la ruta del laboratorio). Requiere Docker
localmente:

```bash
cp .env.example .env            # ajusta GF_SECURITY_ADMIN_PASSWORD
docker compose config           # valida
docker compose build
docker compose up -d
docker compose ps
```

- API: http://localhost:8000  (métricas en `/metrics`)
- Grafana: http://localhost:3000  (admin / el password de tu `.env`)

El resto de servicios son internos a la red `obsnet`. En este modo offline el tracing viene
apagado por defecto (`OTEL_ENABLED=false`); en EC2 el `.env` lo genera el *user-data* con
`OTEL_ENABLED=true`.

## Seguridad

No se versionan credenciales. Usa `.env` (ignorado por git) a partir de `.env.example`. En
EC2 las aplicaciones usan el IAM role `obs-lab-ec2-role`; no se incrustan llaves en el repo
ni en imágenes. El Security Group abre solo 22/3000/8000 a tu IP (`-c allowedCidr`); los
puertos internos (9090/3100/4317/4318/16686) se alcanzan por SSM o túnel SSH.
