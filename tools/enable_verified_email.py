"""Enable the already approved SES test identity after its verification link is clicked."""
import argparse
import json
from pathlib import Path

import boto3
from dotenv import dotenv_values


def enable():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / 'backend' / '.env'
    values = dotenv_values(path)
    if args.email != values.get('SES_VERIFIED_SENDER') or args.email != values.get('ALLOWED_EMAIL_RECIPIENTS'):
        raise RuntimeError('Only the previously approved sender/recipient can be enabled')
    session = boto3.Session(profile_name=values.get('AWS_PROFILE') or None,
                            region_name=values.get('AWS_REGION'))
    if session.client('sts').get_caller_identity()['Account'] != values.get('AWS_ACCOUNT_ID'):
        raise RuntimeError('AWS account mismatch')
    status = session.client('sesv2').get_email_identity(EmailIdentity=args.email)
    if not status['VerifiedForSendingStatus']:
        raise RuntimeError('SES verification is still pending; click the emailed verification link first')
    lines = path.read_text(encoding='utf-8').splitlines()
    lines = ['OUTBOUND_CHANNELS=SES' if line.startswith('OUTBOUND_CHANNELS=') else line for line in lines]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    manifest_path = root / 'aws-connection.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['ses_verified'] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Verified SES test sender enabled. Restart the backend to apply. No email was sent by this script.')


if __name__ == '__main__':
    enable()
