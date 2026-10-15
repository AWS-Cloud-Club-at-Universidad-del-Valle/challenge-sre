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
- `video/` — (opcional) diagrama y videos animados del lab hechos con Remotion (ver [`video/README.md`](./video/README.md)).

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

# Usa TU perfil de AWS CLI (reemplaza <tu-perfil> por el tuyo, p.ej. default):
export AWS_PROFILE=<tu-perfil>

cdk bootstrap                 # solo la primera vez en la cuenta/region
cdk deploy                    # acceso abierto a internet (lab educativo)
# ... usa el lab ...
cdk destroy
```

Para restringir el acceso a tu propia IP: añade
`-c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32` al `cdk deploy`.

Tras `cdk deploy`, abre Grafana en `http://<PublicIp>:3000` (output `GrafanaUrl`).

> Si hay un despliegue activo, las credenciales y comandos de acceso (Grafana, túnel de
> Jaeger, cómo apagar) quedan en `CREDENCIALES.txt` (ignorado por git, no se versiona).

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
ni en imágenes. Por defecto (lab educativo) el Security Group abre 22/3000/8000/16686 a
todo internet (`0.0.0.0/0`); pasa `-c allowedCidr=<ip>/32` para restringirlo a una sola IP.
Los puertos internos (9090/3100/4317/4318) se alcanzan por SSM o túnel SSH. Con acceso
abierto, cambia la contraseña de Grafana y destruye el stack al terminar.
