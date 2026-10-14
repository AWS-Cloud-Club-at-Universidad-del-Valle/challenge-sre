# cdk/ — AWS CDK v2 (Python) app for the obs-lab

This CDK app provisions the whole observability lab on **one** EC2 instance
(t3.small, Amazon Linux 2023, 20 GiB gp3). The instance's cloud-init user-data
installs Docker + the Compose plugin, downloads the lab code (bundled as a CDK
S3 asset), and runs `docker compose up -d` so every service (api, service-b,
Prometheus, Loki, Alloy, Grafana, node_exporter, OTel Collector, Jaeger) comes
up automatically. The full step-by-step tutorials live at the repo root
(`01-metricas-y-logs.md`, `02-trazas-distribuidas-opentelemetry-jaeger.md`);
this file is only a quick reference, not a tutorial.

## Prerequisites

- AWS CLI v2 with the `stay` profile configured (account `550428926318`,
  region `us-east-1`).
- Node.js (for the `cdk` CLI) and Python 3.12 (for this app).
- The CDK CLI: `npm i -g aws-cdk`.

## Setup

```bash
cd cdk
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Commands

Pass your public IP as `allowedCidr` so the Security Group only lets you in:

```bash
# one-time per account/region
cdk bootstrap aws://550428926318/us-east-1 --profile stay

# validate locally (creates nothing)
cdk synth -c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32 --profile stay

# deploy for real (creates the EC2 + supporting resources)
cdk deploy -c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32 --profile stay

# tear everything down
cdk destroy -c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32 --profile stay
```

## Context parameters

- `allowedCidr` (required): the CIDR allowed to reach ports 22/3000/8000.
- `keyName` (default `ec2-docker-api-key`): EC2 key pair; pass `-c keyName=""`
  to omit SSH and use SSM Session Manager only.
- `openApiPort` (default `true`): open port 8000 (the API) to `allowedCidr`.

## Outputs

`cdk deploy` prints the instance public IP, the Grafana URL
(`http://<ip>:3000`), the SSM session command, and the Jaeger port-forward
command (SSM and the SSH `-L` alternative).
