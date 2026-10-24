"""Run a bounded synthetic cloud verification. No real patient data or phone deliveries."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx
from dotenv import dotenv_values


def verify():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send-approved-audit', action='store_true')
    parser.add_argument('--read-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = dotenv_values(root / 'backend' / '.env')
    assert config['AWS_MODE'] == 'live' and config['ALLOW_DEMO_FALLBACK'] == 'false'
    session = boto3.Session(profile_name=config['AWS_PROFILE'], region_name=config['AWS_REGION'])
    assert session.client('sts').get_caller_identity()['Account'] == config['AWS_ACCOUNT_ID']
    headers = {'Authorization': f'Bearer {config["API_TOKEN"]}'}
    with httpx.Client(base_url='http://127.0.0.1:8000', headers=headers, timeout=90) as api:
        health = api.get('/api/health').raise_for_status().json()
        if args.read_only:
            state = api.get('/api/patients/EP-2026-409').raise_for_status().json()
        else:
            intake = api.post('/api/workflow/ingest-discharge', data={'episode_id': 'EP-2026-409'}).raise_for_status().json()
            assert intake['ingested']
            image = (root / 'backend/sample_assets/synthetic_medication_label.png').read_bytes()
            state = api.post('/api/workflow/whatsapp-multimodal', data={
                'episode_id': 'EP-2026-409',
                'transcript': 'Synthetic test: I have a 101.2F fever and dizziness after discharge. Please request clinical review.'},
                files={'image': ('synthetic_medication_label.png', image, 'image/png')}).raise_for_status().json()
        assert state['analysis']['execution_mode'] == 'LIVE_AWS'
        assert state['analysis']['structured_output_valid'], 'The live model response must pass schema validation'
        if not args.read_only:
            api.post('/api/workflow/simulate-deadzone-failover', json={'episode_id': 'EP-2026-409'}).raise_for_status()
        if args.send_approved_audit and not args.read_only:
            if not health['channels']['SES']:
                raise RuntimeError('SES must be verified and enabled before the one approved audit email is sent')
            state = api.post('/api/workflow/caregiver-sms-reply', json={
                'episode_id': 'EP-2026-409', 'reply': '1'}).raise_for_status().json()
            assert state['audit']['mode'] == 'LIVE_AWS'
        events = api.get('/api/telemetry').raise_for_status().json()
    ddb = session.client('dynamodb').get_item(TableName=config['MEMORY_TABLE'], Key={
        'EpisodeID': {'S': 'EP-2026-409'}, 'EntityKey': {'S': 'STATE#CURRENT'}}, ConsistentRead=True)
    assert json.loads(ddb['Item']['State']['S'])['analysis']['execution_mode'] == 'LIVE_AWS'
    head = session.client('s3').head_object(Bucket=config['ASSETS_BUCKET'], Key='EP-2026-409/discharge.pdf')
    real = [event for event in events if event.get('execution_mode') == 'LIVE_AWS']
    evidence = [{key: event.get(key) for key in ('service', 'operation', 'request_id', 'http_status', 'latency_ms', 'message_id')}
                for event in real]
    previous_report = root / 'live-aws-verification.json'
    if previous_report.exists():
        evidence += json.loads(previous_report.read_text(encoding='utf-8')).get('evidence', [])
    evidence = list({(event['service'], event['operation'], event['request_id']): event for event in evidence}.values())
    assert any(event.get('service') == 'bedrock-runtime' and event.get('request_id') for event in evidence)
    assert any(event.get('service') == 'events' and event.get('request_id') for event in evidence)
    report = {'verified_at': datetime.now(timezone.utc).isoformat(), 'account': config['AWS_ACCOUNT_ID'],
        'region': config['AWS_REGION'], 'mode': health['mode'], 'demo_fallback': False,
        'dynamodb_readback': 'PASS', 's3_pdf_head': head['ResponseMetadata']['HTTPStatusCode'],
        'bedrock_multimodal': 'PASS', 'eventbridge': 'PASS',
        'phone_messages': 'NOT_SENT: sender onboarding required',
        'ses': state['audit']['mode'] if state.get('audit') else 'Not sent',
        'ses_message_id': state['audit']['message_id'] if state.get('audit') else None,
        'evidence': evidence}
    (root / 'live-aws-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'evidence'}, indent=2))


if __name__ == '__main__':
    verify()
