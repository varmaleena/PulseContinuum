"""Send one explicitly authorized synthetic handoff, then prove repeats do not resend.

Fixed server destination only. Do not run as a routine regression check.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://pulsecontinuum.vercel.app'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--episode',choices=['EP-2026-409','EP-2026-425','EP-2026-429'],default='EP-2026-409')
    episode = parser.parse_args().episode
    private = json.loads((ROOT/'tmp/hosting-config.json').read_text(encoding='utf-8'))
    db = boto3.Session(profile_name='default',region_name='us-east-1').client('dynamodb',
        config=Config(connect_timeout=5,read_timeout=10,retries={'max_attempts':1}))
    with httpx.Client(base_url=BASE,headers={'Origin':BASE},timeout=60) as api:
        health = api.get('/api/health').raise_for_status().json()
        assert health.get('email_demo_enabled') and health['channels']['SES']
        assert not any(health['channels'][c] for c in ('WHATSAPP','RCS','SMS'))
        state = api.get('/api/patients/'+episode).raise_for_status().json()
        if not state['audit']:
            api.post('/api/workflow/replay-scenario',json={'episode_id':episode}).raise_for_status()
            state = api.post('/api/workflow/rcs-action',json={'episode_id':episode,'option_id':'triage'}).raise_for_status().json()
            assert state['audit']['mode']=='NOT_SENT', 'Review creation must not email automatically'
        assert api.post('/api/workflow/send-demo-email',json={'episode_id':episode,
            'recipient':'unapproved@example.org'}).status_code==422
        sent = api.post('/api/workflow/send-demo-email',json={'episode_id':episode}).raise_for_status().json()
        receipt = sent['email_receipt']
        assert receipt['status']=='ACCEPTED_BY_SES', (receipt['status'],receipt.get('error_code','no code recorded'))
        key = {'EpisodeID':{'S':'BUDGET#'+datetime.now(timezone.utc).strftime('%Y-%m-%d')},'EntityKey':{'S':'SES_DEMO'}}

        def attempts():
            return db.get_item(TableName=private['outputs']['MemoryTable'],Key=key,ConsistentRead=True)['Item']['SendAttempts']['N']

        before = attempts()
        repeated = api.post('/api/workflow/send-demo-email',json={'episode_id':episode}).raise_for_status().json()
        assert repeated['email_receipt']==receipt
        assert attempts()==before
        proof = {'tested_at':datetime.now(timezone.utc).isoformat(),'episode_id':episode,
            'status':receipt['status'],'packet_sha256':receipt['packet_sha256'],
            'destination':'Previously approved verified owner inbox','fixed_recipient_enforced':True,
            'duplicate_request_resends':False,'daily_attempts_after_test':int(before),
            'inbox_delivery_verified':False,'phone_channels_enabled':False,
            'note':'Actual SES acceptance via the public workflow. No claim of inbox delivery or clinical care.'}
        # Public care responses strip AWS IDs; read the durable receipt for sanitized execution evidence.
        record_key = {'EpisodeID':{'S':'EMAIL#'+datetime.now(timezone.utc).strftime('%Y-%m-%d')},'EntityKey':{'S':episode}}
        stored = json.loads(db.get_item(TableName=private['outputs']['MemoryTable'],Key=record_key,
            ConsistentRead=True)['Item']['State']['S'])
        proof.update({k:stored[k] for k in ('message_id','request_id','http_status')})
        (ROOT/'submission/live-demo-email-verification.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
        print('PASS: SES accepted the synthetic PDF email; HTTP',proof['http_status'])
        print('PASS: repeated public request returned the same receipt without another email attempt')
        print('Inbox delivery remains unverified. Phone channels are disabled.')


if __name__ == '__main__':
    main()
