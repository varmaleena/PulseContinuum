import os

import aws_cdk as cdk
from hosted_stack import HostedStack

app = cdk.App()
HostedStack(app, 'PulseContinuumWebBackend', code_bucket=os.environ['PULSE_CODE_BUCKET'],
            code_key=os.environ['PULSE_CODE_KEY'], synthesizer=cdk.BootstraplessSynthesizer(),
            existing_table=os.getenv('EXISTING_HOSTED_TABLE'), existing_bucket=os.getenv('EXISTING_HOSTED_BUCKET'),
            existing_logs=os.getenv('EXISTING_HOSTED_LOGS'),
            env=cdk.Environment(account=os.environ['PULSE_ACCOUNT'], region='us-east-1'))
app.synth()
