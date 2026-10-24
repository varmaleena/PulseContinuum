"""Configure a local, loopback-only app from an already deployed AWS stack.

Uses the AWS credential provider chain; never copies access keys into app files.
"""
import argparse
import json
import secrets
from pathlib import Path

import boto3


def configure():
    parser = argparse.ArgumentParser()
    parser.add_argument('--account', required=True)
    parser.add_argument('--stack', default='PulseContinuumConnected')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--profile', default='default')
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    identity = session.client('sts').get_caller_identity()
    if identity['Account'] != args.account:
        raise RuntimeError('AWS account mismatch; configuration stopped')
    stack = session.client('cloudformation').describe_stacks(StackName=args.stack)['Stacks'][0]
    if stack['StackStatus'] not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE'):
        raise RuntimeError(f'Stack is not ready: {stack["StackStatus"]}')
    outputs = {entry['OutputKey']: entry['OutputValue'] for entry in stack['Outputs']}
    email = session.client('sesv2').get_email_identity(EmailIdentity=args.email)
    email_enabled = email['VerifiedForSendingStatus']
    token = secrets.token_urlsafe(48)
    values = {
        'AWS_MODE': 'live', 'AWS_REGION': args.region, 'AWS_PROFILE': args.profile,
        'AWS_ACCOUNT_ID': args.account, 'ALLOW_DEMO_FALLBACK': 'false',
        'MEMORY_TABLE': outputs['MemoryTable'], 'ASSETS_BUCKET': outputs['AssetsBucket'],
        'INBOUND_QUEUE_URL': outputs['InboundQueueUrl'], 'EVENT_BUS_NAME': 'default',
        'BEDROCK_MODEL_ID': 'us.amazon.nova-pro-v1:0',
        'OUTBOUND_CHANNELS': 'SES' if email_enabled else '',
        'SES_VERIFIED_SENDER': args.email, 'ALLOWED_EMAIL_RECIPIENTS': args.email,
        'TEST_PHYSICIAN_EMAIL': args.email, 'API_TOKEN': token,
        'WEBHOOK_TOKEN': secrets.token_urlsafe(48), 'AUDIT_SIGNING_KEY': secrets.token_urlsafe(48),
        'DATA_DIR': '.data-live',
    }
    backend_env = root / 'backend' / '.env'
    frontend_env = root / 'frontend' / '.env.local'
    if backend_env.exists() or frontend_env.exists():
        raise RuntimeError('Configuration already exists. Preserve existing secrets and edit it explicitly.')
    backend_env.write_text('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n', encoding='utf-8')
    frontend_env.write_text(f'BACKEND_URL=http://127.0.0.1:8000\nBACKEND_API_TOKEN={token}\n', encoding='utf-8')
    # This manifest intentionally contains no authentication material.
    manifest = {'account': args.account, 'region': args.region, 'stack': args.stack,
                'storage': outputs, 'ses_verified': email_enabled,
                'phone_channels': 'Not enabled: account onboarding required',
                'demo_fallback': False}
    (root / 'aws-connection.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'configured': True, 'account': args.account, 'ses_enabled': email_enabled,
                      'secrets': 'Generated locally; not displayed'}))


if __name__ == '__main__':
    configure()
