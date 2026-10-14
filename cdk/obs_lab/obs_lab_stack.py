"""ObsLabStack — provisions one EC2 that auto-boots the docker-compose lab.

The stack creates: the default VPC (lookup) + a public subnet, a least-privilege
Security Group (22/3000/16686/optional-8000 from the caller's CIDR), an IAM role
with AmazonSSMManagedInstanceCore (NO X-Ray), a t3.small Amazon Linux 2023
instance with a 20 GiB gp3 root volume, an S3 asset bundling the lab code, and
cloud-init user-data that installs Docker + the Compose plugin, pulls+unpacks
the asset to /opt/obs-lab, writes .env (OTEL_ENABLED=true), and runs
`docker compose up -d`.
"""
import os

from aws_cdk import (
    CfnOutput,
    Stack,
    Tags,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3_assets as s3_assets,
)
from constructs import Construct

# Pinned docker compose v2 plugin version installed on the instance.
COMPOSE_VERSION = "v2.29.7"

# Repo root relative to this file (cdk/obs_lab/obs_lab_stack.py -> repo root).
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class ObsLabStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Access scope -----------------------------------------------------
        # Educational lab: by default the UIs are open to the whole internet
        # (0.0.0.0/0). Pass -c allowedCidr=<ip>/32 to restrict access to a
        # single IP instead. publicAccess defaults to True.
        allowed_cidr = self.node.try_get_context("allowedCidr")
        public_access = self.node.try_get_context("publicAccess")
        if isinstance(public_access, str):
            public_access = public_access.lower() not in ("false", "0", "no")
        if not allowed_cidr:
            if public_access is False:
                raise ValueError(
                    "publicAccess is disabled but no allowedCidr was given. "
                    "Pass your public IP, e.g. "
                    "-c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32"
                )
            allowed_cidr = "0.0.0.0/0"

        # Optional context ----------------------------------------------------
        key_name = self.node.try_get_context("keyName")
        if key_name == "":
            key_name = None  # explicit empty => SSM-only, no SSH key pair

        open_api_port = self.node.try_get_context("openApiPort")
        # context values are strings/bools; default to True when unset
        if open_api_port is None:
            open_api_port = True
        elif isinstance(open_api_port, str):
            open_api_port = open_api_port.lower() not in ("false", "0", "no")

        # --- VPC + public subnet ---------------------------------------------
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)
        public_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)

        # --- Security Group ---------------------------------------------------
        sg = ec2.SecurityGroup(
            self,
            "ObsLabSg",
            vpc=vpc,
            security_group_name="obs-lab-sg",
            description="obs-lab: SSH + Grafana + Jaeger (+optional API)",
            allow_all_outbound=True,
        )
        peer = ec2.Peer.ipv4(allowed_cidr)
        scope_desc = "anywhere" if allowed_cidr == "0.0.0.0/0" else "allowed CIDR"
        sg.add_ingress_rule(peer, ec2.Port.tcp(22), f"SSH from {scope_desc}")
        sg.add_ingress_rule(peer, ec2.Port.tcp(3000), f"Grafana UI from {scope_desc}")
        # Jaeger UI reachable directly by public IP (educational lab, no tunnel).
        sg.add_ingress_rule(peer, ec2.Port.tcp(16686), f"Jaeger UI from {scope_desc}")
        if open_api_port:
            sg.add_ingress_rule(peer, ec2.Port.tcp(8000), f"API from {scope_desc}")
        # Ports 9090/3100/4317/4318 stay on the internal docker network only;
        # they are reached via SSM/SSH tunnel if ever needed.

        # --- IAM role (SSM only; NO X-Ray) -----------------------------------
        role = iam.Role(
            self,
            "ObsLabEc2Role",
            role_name="obs-lab-ec2-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        # --- Code asset (bundled lab repo) -----------------------------------
        asset = s3_assets.Asset(
            self,
            "LabCode",
            path=REPO_ROOT,
            exclude=[
                ".git",
                ".venv",
                "__pycache__",
                "*.pyc",
                ".pytest_cache",
                ".env",
                ".agents",
                "cdk/cdk.out",
                "cdk/.venv",
                "node_modules",
            ],
        )

        # --- User-data --------------------------------------------------------
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(*self._user_data_commands(asset))

        # --- EC2 instance -----------------------------------------------------
        instance = ec2.Instance(
            self,
            "ObsLabInstance",
            instance_type=ec2.InstanceType("t3.small"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=public_subnets,
            security_group=sg,
            role=role,
            user_data=user_data,
            associate_public_ip_address=True,
            key_name=key_name,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        20, volume_type=ec2.EbsDeviceVolumeType.GP3
                    ),
                )
            ],
        )
        Tags.of(instance).add("Name", "obs-lab-ec2")

        # Least-privilege S3 read on the asset for the instance role.
        asset.grant_read(instance.role)

        # --- Outputs ----------------------------------------------------------
        CfnOutput(
            self,
            "PublicIp",
            value=instance.instance_public_ip,
            description="Public IPv4 of the obs-lab EC2 instance",
        )
        CfnOutput(
            self,
            "PublicDnsName",
            value=instance.instance_public_dns_name,
            description="Public DNS name of the obs-lab EC2 instance",
        )
        CfnOutput(
            self,
            "GrafanaUrl",
            value=f"http://{instance.instance_public_ip}:3000",
            description="Grafana UI (admin / password from the generated .env)",
        )
        CfnOutput(
            self,
            "SsmSessionCommand",
            value=(
                f"aws ssm start-session --target {instance.instance_id} "
                "--profile stay"
            ),
            description="Open an SSM shell on the instance (no SSH key needed)",
        )
        CfnOutput(
            self,
            "JaegerUrl",
            value=f"http://{instance.instance_public_ip}:16686",
            description="Jaeger UI (open directly by public IP; scoped to your CIDR)",
        )

    def _user_data_commands(self, asset: s3_assets.Asset) -> list:
        """Return the cloud-init shell lines that boot the compose stack.

        The asset bucket/key are CDK tokens; interpolating them into the shell
        strings makes the synthesized template carry the real references.
        """
        return [
            "set -euxo pipefail",
            "dnf update -y",
            "dnf install -y docker unzip",
            "systemctl enable --now docker",
            "usermod -aG docker ec2-user",
            # docker compose v2 plugin
            "mkdir -p /usr/local/lib/docker/cli-plugins",
            (
                'curl -SL "https://github.com/docker/compose/releases/download/'
                f'{COMPOSE_VERSION}/docker-compose-linux-x86_64" '
                "-o /usr/local/lib/docker/cli-plugins/docker-compose"
            ),
            "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose",
            # fetch the lab code from the CDK asset bucket
            "mkdir -p /opt/obs-lab",
            (
                f"aws s3 cp s3://{asset.s3_bucket_name}/{asset.s3_object_key} "
                f"/tmp/lab.zip --region {self.region}"
            ),
            "unzip -o /tmp/lab.zip -d /opt/obs-lab",
            # .env with tracing ON by default for the EC2 lab
            "cat > /opt/obs-lab/.env <<'ENV'",
            "GF_SECURITY_ADMIN_PASSWORD=changeme",
            "OTEL_ENABLED=true",
            "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317",
            "LOAD_TEST_RATE=3",
            "LOAD_TEST_DURATION=60",
            "ENV",
            # idempotent bring-up
            "cd /opt/obs-lab",
            "docker compose build",
            "docker compose up -d",
        ]
