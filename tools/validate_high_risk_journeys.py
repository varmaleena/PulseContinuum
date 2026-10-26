"""Three real hosted synthetic journeys; bounded inference, no outbound email/phone sends."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT/'tmp/hosting-config.json').read_text(encoding='utf-8'))
    scenarios = json.loads((ROOT/'backend/sample_assets/high_risk_scenarios.json').read_text(encoding='utf-8'))
    session = boto3.Session(profile_name='default',region_name='us-east-1')
    database, storage = session.client('dynamodb'), session.client('s3')
    table, bucket = config['outputs']['MemoryTable'], config['outputs']['AssetsBucket']
    report = {'tested_at':datetime.now(timezone.utc).isoformat(),'scope':'Synthetic hosted engineering verification; no clinical efficacy or recovery claim',
              'cases':[],'outbound_messages_sent':0}

    def allowance():
        item = database.get_item(TableName=table,Key={
            'EpisodeID':{'S':'BUDGET#'+datetime.now(timezone.utc).strftime('%Y-%m-%d')},'EntityKey':{'S':'BEDROCK'}}).get('Item',{})
        return int(item.get('ModelCalls',{}).get('N','0'))

    with httpx.Client(base_url=config['outputs']['BackendUrl'],timeout=65,
                      headers={'Authorization':'Bearer '+config['api_token']}) as api:
        backup = api.get('/api/patients').raise_for_status().json()
        (ROOT/'tmp/pre-journey-qa-backup.json').write_text(json.dumps(backup,indent=2),encoding='utf-8')
        before = allowance()
        report['model_attempts_before'] = before
        for scenario in scenarios:
            episode = scenario['episode_id']
            result = {'episode_id':episode,'title':scenario['title'],'checks':{},'requests':[]}

            def request(method,path,expected=200,**kwargs):
                started = time.perf_counter()
                response = api.request(method,path,**kwargs)
                result['requests'].append({'method':method,'path':path,'status':response.status_code,
                    'elapsed_ms':round((time.perf_counter()-started)*1000,1),'expected':expected})
                if response.status_code != expected:
                    raise RuntimeError(f'{episode}: {path} returned {response.status_code}: {response.text[:350]}')
                return response

            request('POST','/api/workflow/reset',json={'episode_id':episode})
            intake = request('POST','/api/workflow/ingest-discharge',data={'episode_id':episode}).json()
            files = {}
            if scenario['image']:
                files['image'] = (scenario['image'],(ROOT/'backend/sample_assets'/scenario['image']).read_bytes(),'image/png')
            state = request('POST','/api/workflow/whatsapp-multimodal',data={
                'episode_id':episode,'transcript':scenario['transcript']},files=files).json()
            assert state['analysis']['execution_mode']=='LIVE_AWS'
            assert state['analysis']['structured_output_valid']
            assert state['risk_score']>=82 and state['analysis']['review_required']
            assert [card['id'] for card in state['rcs_cards']]==['triage']
            assert all(message['status']=='NOT_SENT' for message in state['messages'] if message['direction']=='outbound')
            events = request('GET','/api/telemetry').json()
            inference = [event for event in events if event.get('service')=='bedrock-runtime' and event.get('operation')=='converse'
                         and event.get('execution_mode')=='LIVE_AWS'][-1]
            assert inference.get('request_id') and inference.get('http_status')==200
            evidence = {'recorded_at':datetime.now(timezone.utc).isoformat(),'model_request_id':inference['request_id'],
                        'scenario':scenario,'state':state}
            storage.put_object(Bucket=bucket,Key=f'scenarios/{episode}.json',
                               Body=json.dumps(evidence).encode(),ContentType='application/json')
            result['model_request_id'] = inference['request_id']
            result['analysis_ms'] = result['requests'][-2]['elapsed_ms']
            result['checks']['real_validated_inference'] = True
            for option in ('generic','brand'):
                request('POST','/api/workflow/rcs-action',expected=422,json={'episode_id':episode,'option_id':option})
            result['checks']['unapproved_medication_actions_blocked'] = True
            request('POST','/api/workflow/acknowledge-plan',expected=422,json={'episode_id':episode,
                'actor':'CAREGIVER','teach_back':'Synthetic: I understand a review is needed.'})
            request('POST','/api/workflow/follow-up',expected=422,json={'episode_id':episode,'outcome':'CONTACT_RECORDED',
                'note':'Synthetic attempted follow-up without the required review/acknowledgment.'})
            if scenario['fallback']:
                fallback = request('POST','/api/workflow/simulate-deadzone-failover',json={'episode_id':episode}).json()
                assert len([m for m in fallback['messages'] if m['channel']=='SMS'])==2
                assert all(m['status']=='NOT_SENT' for m in fallback['messages'] if m['channel']=='SMS')
                request('POST','/api/workflow/caregiver-sms-reply',json={'episode_id':episode,'reply':'2'})
                result['checks']['caregiver_fallback_preserves_context_without_fake_delivery'] = True
            else:
                request('POST','/api/workflow/rcs-action',json={'episode_id':episode,'option_id':'triage'})
            request('POST','/api/workflow/clinical-review',expected=422,json={'episode_id':episode,
                'decision':'FOLLOW_DISCHARGE_PLAN','notes':'Synthetic attempt to clear a symptomatic episode without assessment.'})
            request('POST','/api/workflow/clinical-review',json={'episode_id':episode,'decision':'CLINICIAN_CONTACT',
                'notes':'SYNTHETIC QA: Reviewed the report and requested treating-team assessment. No medication change is authorized by the app.'})
            request('POST','/api/workflow/acknowledge-plan',json={'episode_id':episode,
                'actor':'CAREGIVER' if scenario['fallback'] else 'PATIENT',
                'teach_back':'SYNTHETIC QA: I understand that the treating clinical team must assess this report. The app has not changed any medication.'})
            final = request('POST','/api/workflow/follow-up',json={'episode_id':episode,
                'outcome':'REASSESSMENT_REQUESTED' if scenario['fallback'] else 'CONTACT_RECORDED',
                'note':'SYNTHETIC QA: Follow-up communication was recorded. Actual assessment and recovery are not independently verified.'}).json()
            assert final['medications']==intake['medications']
            assert final['clinical_review']['simulation'] and not final['clinical_review']['medication_changes_made']
            assert not final['follow_up_record']['recovery_verified']
            assert final['audit']['mode']=='NOT_SENT' and not final['audit']['message_id']
            assert hashlib.sha256(final['audit']['canonical_payload'].encode()).hexdigest()==final['audit']['sha256']
            pdf = request('GET',final['audit']['pdf_url'])
            assert pdf.content.startswith(b'%PDF')
            result['checks'].update({'ordered_review_acknowledgment_followup':True,'medications_unchanged':True,
                'recovery_not_fabricated':True,'handoff_hash_verified':True,'handoff_pdf_downloaded':True,'no_email_sent':True})
            model_count = allowance()
            restored = request('POST','/api/workflow/replay-scenario',json={'episode_id':episode}).json()
            assert restored['analysis']['execution_mode']=='RECORDED_AWS_RUN'
            assert restored['clinical_review'] is None and restored['order'] is None
            assert allowance()==model_count
            result['checks']['recorded_replay_does_not_consume_inference_allowance'] = True
            result['passed'] = all(result['checks'].values())
            report['cases'].append(result)
            print(episode+': PASS '+str(len(result['checks']))+' checks',flush=True)
        report['model_attempts_after'] = allowance()
        assert report['model_attempts_after']-before==3
        catalog = api.get('/api/scenarios').raise_for_status().json()
        assert len([row for row in catalog if row['available']])==3
    report['summary'] = {'scenarios_passed':sum(case['passed'] for case in report['cases']),
                         'total_scenarios':3,'new_live_inference_attempts':3,'recorded_replays_verified':3}
    (ROOT/'submission/high-risk-journey-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    main()
