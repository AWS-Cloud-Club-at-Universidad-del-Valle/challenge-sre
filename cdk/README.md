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

- AWS CLI v2 with a profile configured for your own account (region `us-east-1`
  by default; override with `CDK_DEFAULT_REGION`).
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

Set your AWS CLI profile once (replace `<your-profile>`, e.g. `default`):

```bash
export AWS_PROFILE=<your-profile>

# one-time per account/region
cdk bootstrap

# validate locally (creates nothing)
cdk synth

# deploy for real (creates the EC2 + supporting resources)
# Access is open to the internet (0.0.0.0/0) by default for this educational lab.
cdk deploy

# tear everything down
cdk destroy
```

To restrict access to your own IP instead of the whole internet, add
`-c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32` to `cdk deploy`.

## Context parameters

- `allowedCidr` (optional): restrict ports 22/3000/8000/16686 to this CIDR.
  Omitted => open to `0.0.0.0/0` (educational default).
- `keyName` (optional, default none): by default there is NO SSH key pair and
  you access the instance via SSM Session Manager (works in any account). Pass
  `-c keyName=<your-existing-key-pair>` only if you want SSH and already created
  that key pair in your account.
- `openApiPort` (default `true`): open port 8000 (the API) to `allowedCidr`.

## Outputs

`cdk deploy` prints the instance public IP, the Grafana URL
(`http://<ip>:3000`), the SSM session command, and the Jaeger port-forward
command (SSM and the SSH `-L` alternative).
