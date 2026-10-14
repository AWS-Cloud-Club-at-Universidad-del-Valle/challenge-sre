# Parte 1 — Métricas y Logs (CDK + Grafana)

Despliegas todo en AWS con **un solo comando de CDK**. La EC2 arranca sola e instala
Docker con todos los servicios (API, Prometheus, Loki, Grafana, node_exporter). Tú solo
entras a Grafana y creas dos dashboards: **CPU** y **respuestas de la API**.

> La Parte 2 (trazas con OpenTelemetry y Jaeger) está en
> [`02-trazas-distribuidas-opentelemetry-jaeger.md`](./02-trazas-distribuidas-opentelemetry-jaeger.md)
> y usa la **misma** instancia (no vuelves a desplegar).

---

## 1. Arquitectura (resumen)

```mermaid
flowchart LR
    DEV["Tú (cdk deploy)"] --> CFN["CloudFormation"]
    CFN --> EC2["EC2 t3.small (Amazon Linux 2023)"]
    subgraph EC2
      API["API FastAPI :8000"]
      NODE["node_exporter"]
      PROM["Prometheus"]
      LOKI["Loki + Alloy"]
      GRAF["Grafana :3000"]
    end
    NODE --> PROM
    API --> PROM
    API --> LOKI
    PROM --> GRAF
    LOKI --> GRAF
    DEV -- "navegador" --> GRAF
```

**Grafana (3000)**, la **API (8000)** y **Jaeger (16686, Parte 2)** se exponen a tu IP. El
resto (Prometheus, Loki, OTel) queda interno.

---

## 2. Requisitos previos

- **AWS CLI** con el perfil `stay` configurado (`aws sts get-caller-identity --profile stay`).
- **Node.js** y el CDK CLI: `npm install -g aws-cdk` (comprueba con `cdk --version`).
- **Python 3.12+**.

---

## 3. Desplegar con CDK

Desde la carpeta `cdk/`:

```bash
cd cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Solo la primera vez en la cuenta/región:
cdk bootstrap --profile stay

# Despliega (acceso abierto a internet por defecto, lab educativo):
cdk deploy --profile stay --require-approval never
```

> **Acceso.** Por defecto el lab abre Grafana, Jaeger y la API a todo internet
> (`0.0.0.0/0`) para que sea fácil de usar en clase. Si prefieres restringir a tu propia IP,
> añade `-c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32` al comando.

**Resultado esperado:** al terminar (~3 min) CDK imprime las *Outputs*, entre ellas:

```
ObsLabStack.GrafanaUrl = http://<IP-PUBLICA>:3000
ObsLabStack.SsmSessionCommand = aws ssm start-session --target <ID> --profile stay
```

Anota la `GrafanaUrl`. La EC2 sigue instalando los contenedores unos minutos más.

**Cómo comprobar que ya levantó todo** (reemplaza `<ID>` por el de la Output):

```bash
aws ssm start-session --target <ID> --profile stay
# ya dentro de la instancia:
docker ps        # debes ver 9 contenedores "Up"
exit
```

Si `docker ps` aún no muestra todo, espera 1–2 min: el *user-data* sigue arrancando.

---

## 4. Entrar a Grafana

1. Abre en el navegador la `GrafanaUrl` (ej. `http://<IP-PUBLICA>:3000`).
2. Usuario `admin`, contraseña `changeme`.

> Con acceso abierto, **cambia la contraseña** de Grafana (menú de perfil → *Change
> password*) para que no quede expuesta con el valor por defecto.

---

## 5. Dashboard de CPU

> `node_exporter` mide el **sistema operativo** de la EC2 (CPU, memoria, disco, red). **No
> es Amazon CloudWatch** (eso es un servicio aparte de AWS). Aquí todas las métricas de
> infraestructura vienen de `node_exporter`.

1. **Dashboards → New → New dashboard → Add visualization**.
2. Fuente de datos: **Prometheus**.
3. Pega esta consulta (uso de CPU en %):

   ```promql
   100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
   ```

4. Panel: `Time series`, **Unit** `Percent (0-100)`, **Title** "Uso de CPU (%)".
5. **Apply** → arriba fija *refresh* `10s` → **Save dashboard** ("CPU de la instancia").

**Resultado esperado:** una línea con el % de CPU. Sube al generar tráfico (paso 7).

---

## 6. Dashboard de respuestas de la API

Crea otro dashboard (**Dashboards → New**) y añade un panel por cada consulta. Todos usan
la fuente **Prometheus**.

**Solicitudes por segundo** — `Stat`:
```promql
sum(rate(api_requests_total[5m]))
```

**Solicitudes por endpoint** — `Time series`, leyenda `{{route}}`:
```promql
sum by (route) (rate(api_requests_total[5m]))
```

**Latencia p50/p90/p99** — `Time series`, unidad `s`. Añade 3 queries cambiando `0.50`,
`0.90`, `0.99`:
```promql
histogram_quantile(0.90, sum by (le) (rate(api_request_duration_seconds_bucket[5m])))
```

**Códigos HTTP 2xx/4xx/5xx** — `Time series`, leyenda `{{status_class}}`:
```promql
sum by (status_class) (rate(api_requests_by_status_class_total[5m]))
```

**Tasa de error (5xx)** — `Stat`, unidad `percent (0-100)`:
```promql
100 * sum(rate(api_requests_by_status_class_total{status_class="5xx"}[5m]))
      / sum(rate(api_requests_total[5m]))
```

**Save dashboard** ("Respuestas de la API").

> Ya hay dashboards equivalentes provisionados automáticamente
> (`config/grafana/dashboards/`). Este ejercicio es para que entiendas las consultas.

---

## 7. Generar tráfico y ver los dashboards moverse

Desde tu equipo, apuntando a la IP pública de la instancia:

```bash
cd scripts
python3 load_test.py --base-url http://<IP-PUBLICA>:8000 --duration 120
```

Genera llamadas con éxito, 404 y errores 500. **Resultado esperado:** en Grafana ves subir
las req/s, aparecen barras 4xx/5xx y la CPU sube.

---

## 8. Ver los logs (Loki)

En Grafana: **Explore → fuente Loki → ** consulta:

```logql
{service="obs-lab-api"}
```

**Resultado esperado:** logs JSON con `method`, `route`, `status` y `trace_id`. En la Parte
2 usarás ese `trace_id` para saltar a la traza en Jaeger.

---

## 9. Seguridad y puertos

| Puerto | Servicio | Acceso |
|---|---|---|
| 22 | SSH | Abierto (o usa SSM, sin llaves) |
| 3000 | Grafana | Abierto a internet (`0.0.0.0/0`) |
| 8000 | API | Abierto a internet |
| 16686 | Jaeger (trazas, Parte 2) | Abierto a internet |
| 9090/3100/4317 | Prometheus/Loki/OTel | **Cerrados** (internos; vía túnel SSM si hace falta) |

> Lab educativo: por defecto todo está abierto a internet. Es cómodo para clase pero deja
> Grafana (cambia su contraseña) y Jaeger (sin login) visibles para cualquiera. **Destruye
> el stack al terminar.** Para restringir a tu IP: `-c allowedCidr=<tu-ip>/32`.

---

## 10. Costes y limpieza

Mientras la EC2 esté encendida genera coste (~$15/mes si queda 24/7, + EBS + IP). Para
**apagar y dejar de pagar todo**:

```bash
cd cdk
cdk destroy --profile stay
```

> Un simple *stop* de la EC2 **no** borra el disco EBS ni la IP: seguirían costando.
> `cdk destroy` elimina EC2 + EBS + IP + Security Group + IAM de una sola vez.

---

## 11. Si algo falla

- **Grafana no carga:** espera 1–2 min a que el user-data termine, y confirma que usas la
  IP de la Output `GrafanaUrl`.
- **`docker ps` incompleto:** el user-data sigue arrancando; espera 1–2 min. Logs:
  `sudo tail -f /var/log/cloud-init-output.log` (dentro de la instancia por SSM).
- **Panel "No data":** revisa en Prometheus (interno) que los *targets* estén `up`, o
  simplemente genera tráfico (paso 7) y amplía el rango de tiempo a "últimos 15 min".
