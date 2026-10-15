#!/usr/bin/env python3
"""CDK v2 app entrypoint for the obs-lab.

Instantiates a single ObsLabStack that auto-provisions one EC2 instance whose
cloud-init user-data boots the existing docker-compose observability stack.
"""
import os

import aws_cdk as cdk

from obs_lab.obs_lab_stack import ObsLabStack

app = cdk.App()

# Resolve the target account/region from the ambient CDK environment, which the
# CLI sets from the active AWS profile (AWS_PROFILE or --profile). This way the
# stack always deploys to the student's own account, never a hardcoded one.
account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

ObsLabStack(
    app,
    "ObsLabStack",
    env=cdk.Environment(account=account, region=region),
)

# Tag every resource in the app so the lab is easy to find and clean up.
cdk.Tags.of(app).add("Project", "obs-lab")

app.synth()
