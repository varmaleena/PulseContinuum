import os

import aws_cdk as cdk
from pulse_stack import PulseStack

app = cdk.App()
PulseStack(app, os.getenv('PULSE_STACK_NAME', 'PulseContinuumAI'),
           existing_table_name=os.getenv('EXISTING_MEMORY_TABLE'),
           existing_bucket_name=os.getenv('EXISTING_ASSETS_BUCKET'),
           synthesizer=cdk.BootstraplessSynthesizer())
app.synth()
