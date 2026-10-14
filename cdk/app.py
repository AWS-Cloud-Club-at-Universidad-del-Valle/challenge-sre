#!/usr/bin/env python3
"""CDK v2 app entrypoint for the obs-lab.

Instantiates a single ObsLabStack that auto-provisions one EC2 instance whose
cloud-init user-data boots the existing docker-compose observability stack.
"""
import os

import aws_cdk as cdk

from obs_lab.obs_lab_stack import ObsLabStack

app = cdk.App()

# Prefer the ambient CDK environment (set by the CLI from the active profile)
# so `from_lookup` resolves against the student's real account/region. Fall
# back to the pre-verified lab account/region when running offline.
account = os.environ.get("CDK_DEFAULT_ACCOUNT", "550428926318")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

ObsLabStack(
    app,
    "ObsLabStack",
    env=cdk.Environment(account=account, region=region),
)

# Tag every resource in the app so the lab is easy to find and clean up.
cdk.Tags.of(app).add("Project", "obs-lab")

app.synth()
