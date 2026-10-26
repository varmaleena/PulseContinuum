"""Credential-free HTTP journey checks against the public synthetic demo; no model invocations."""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = 'https://pulsecontinuum.vercel.app'
    report = {'tested_at':datetime.now(timezone.utc).isoformat(),'url':base,
              'authentication':'none','new_model_requests':0,'cases':[]}
    with httpx.Client(base_url=base,headers={'Origin':base},timeout=60,follow_redirects=False) as api:
        assert api.get('/overview').status_code==200
        assert api.get('/login').status_code==307
        scenarios = api.get('/api/scenarios').raise_for_status().json()
        assert len(scenarios)==3 and all(scenario['available'] for scenario in scenarios)
        for scenario in scenarios:
            episode = scenario['episode_id']
            state = api.post('/api/workflow/replay-scenario',json={'episode_id':episode}).raise_for_status().json()
            assert state['analysis']['execution_mode']=='RECORDED_AWS_RUN'
            assert not state['order'] and not state['clinical_review']
            assert api.post('/api/workflow/rcs-action',json={'episode_id':episode,'option_id':'generic'}).status_code==422
            if scenario['fallback']:
                state = api.post('/api/workflow/simulate-deadzone-failover',json={'episode_id':episode}).raise_for_status().json()
                sms = [message for message in state['messages'] if message['channel']=='SMS']
                assert len(sms)==2 and all(message['status']=='NOT_SENT' for message in sms)
                assert all('nurse + meds' not in message['text'] for message in sms)
                api.post('/api/workflow/caregiver-sms-reply',json={'episode_id':episode,'reply':'2'}).raise_for_status()
            else:
                api.post('/api/workflow/rcs-action',json={'episode_id':episode,'option_id':'triage'}).raise_for_status()
            api.post('/api/workflow/clinical-review',json={'episode_id':episode,'decision':'CLINICIAN_CONTACT',
                'notes':'SYNTHETIC public-demo QA: assessment requested; no medication change or verified consultation.'}).raise_for_status()
            api.post('/api/workflow/acknowledge-plan',json={'episode_id':episode,'actor':'CAREGIVER',
                'teach_back':'SYNTHETIC public-demo QA: I understand that assessment is needed; the app has not changed medication.'}).raise_for_status()
            state = api.post('/api/workflow/follow-up',json={'episode_id':episode,
                'outcome':'REASSESSMENT_REQUESTED' if scenario['fallback'] else 'CONTACT_RECORDED',
                'note':'SYNTHETIC public-demo QA: contact recorded; clinical assessment and recovery remain unverified.'}).raise_for_status().json()
            assert state['clinical_review']['simulation']
            assert not state['follow_up_record']['recovery_verified']
            assert state['audit']['mode']=='NOT_SENT'
            assert api.get(state['audit']['pdf_url']).raise_for_status().content.startswith(b'%PDF')
            report['cases'].append({'episode_id':episode,'passed':True,'final_status':state['order']['status']})
            print(episode+': public no-login handoff PASS',flush=True)
            api.post('/api/workflow/replay-scenario',json={'episode_id':episode}).raise_for_status()
        api.post('/api/profile',json={'profile':'admin'}).raise_for_status()
        for path in ['/agentcore','/telemetry','/api/telemetry']:
            api.get(path).raise_for_status()
        api.post('/api/profile',json={'profile':'care'}).raise_for_status()
    report['admin_view_switch']='PASS'
    (ROOT/'submission/public-journey-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Public judge demo: 3/3 cases passed without credentials or fresh model calls')


if __name__ == '__main__':
    main()
