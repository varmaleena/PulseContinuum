"""Deploy reviewed CDK backend with secret parameters and persist only private local outputs."""
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]


def main():
    session = boto3.Session(profile_name='default', region_name='us-east-1')
    account = session.client('sts').get_caller_identity()['Account']
    if account != '160885292760':
        raise RuntimeError('Deployment account mismatch')
    private = ROOT / 'tmp/hosting-config.json'
    if private.exists():
        config = json.loads(private.read_text(encoding='utf-8'))
    else:
        config = {'api_token':secrets.token_urlsafe(48), 'signing_key':secrets.token_urlsafe(48),
                  'admin_username':'judge', 'admin_password':secrets.token_urlsafe(24),
                  'care_username':'care', 'care_password':secrets.token_urlsafe(24)}
        private.write_text(json.dumps(config,indent=2),encoding='utf-8')
    # Manifest formats have changed; CloudFormation outputs are the source of truth.
    cf = session.client('cloudformation')
    stack = cf.describe_stacks(StackName='PulseContinuumConnected')['Stacks'][0]
    outputs = {row['OutputKey']:row['OutputValue'] for row in stack['Outputs']}
    bucket = outputs['AssetsBucket']
    package = ROOT / 'dist/backend-lambda.zip'
    key = 'hosting/code/'+hashlib.sha256(package.read_bytes()).hexdigest()+'.zip'
    session.client('s3').upload_file(str(package), bucket, key)
    env = {**os.environ, 'PULSE_CODE_BUCKET':bucket, 'PULSE_CODE_KEY':key, 'PULSE_ACCOUNT':account,
           'CDK_OUTDIR':str(ROOT / 'tmp/hosted-cdk'), 'NODE_OPTIONS':'--max-old-space-size=512'}
    try:
        retained = cf.list_stack_resources(StackName='PulseContinuumHosted')['StackResourceSummaries']
        for resource in retained:
            if resource['ResourceStatus'] == 'DELETE_SKIPPED':
                name = {'AWS::DynamoDB::Table':'EXISTING_HOSTED_TABLE', 'AWS::S3::Bucket':'EXISTING_HOSTED_BUCKET',
                        'AWS::Logs::LogGroup':'EXISTING_HOSTED_LOGS'}.get(resource['ResourceType'])
                if name:
                    env[name] = resource['PhysicalResourceId']
    except ClientError:
        pass
    subprocess.run([sys.executable,'hosted_app.py'],cwd=ROOT/'infra',env=env,check=True)
    template = (ROOT/'tmp/hosted-cdk/PulseContinuumWebBackend.template.json').read_text(encoding='utf-8')
    arguments = {'StackName':'PulseContinuumWebBackend', 'TemplateBody':template,
        'Parameters':[{'ParameterKey':'ApiToken','ParameterValue':config['api_token']},
                      {'ParameterKey':'SigningKey','ParameterValue':config['signing_key']}],
        'Capabilities':['CAPABILITY_IAM']}
    try:
        cf.describe_stacks(StackName=arguments['StackName'])
        existing = True
    except ClientError as exc:
        if 'does not exist' not in str(exc):
            raise
        existing = False
    if existing:
        try:
            cf.update_stack(**arguments)
            cf.get_waiter('stack_update_complete').wait(StackName=arguments['StackName'],WaiterConfig={'Delay':5,'MaxAttempts':120})
        except ClientError as exc:
            if 'No updates are to be performed' not in str(exc):
                raise
    else:
        cf.create_stack(**arguments)
        print('Creating PulseContinuumWebBackend backend stack',flush=True)
        cf.get_waiter('stack_create_complete').wait(StackName=arguments['StackName'],WaiterConfig={'Delay':5,'MaxAttempts':120})
    stack = cf.describe_stacks(StackName=arguments['StackName'])['Stacks'][0]
    config['outputs'] = {row['OutputKey']:row['OutputValue'] for row in stack['Outputs']}
    private.write_text(json.dumps(config,indent=2),encoding='utf-8')
    (ROOT/'submission/PRIVATE_JUDGE_ACCESS.md').write_text(
        '# Private demonstration access\n\nShare only with authorized judges.\n\n'
        f'Care username: {config["care_username"]}\n\nCare password: {config["care_password"]}\n\n'
        f'Admin username: {config["admin_username"]}\n\nAdmin password: {config["admin_password"]}\n',encoding='utf-8')
    print('Backend stack:',stack['StackStatus'])
    print('Backend URL:',config['outputs']['BackendUrl'])
    print('Private access instructions saved locally; no credentials printed.')


if __name__ == '__main__':
    main()
