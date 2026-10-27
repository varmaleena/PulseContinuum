"""Exercise three public synthetic coordination failure paths. No model calls or sends."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://pulsecontinuum.vercel.app'


def main():
    report = {'tested_at':datetime.now(timezone.utc).isoformat(), 'url':BASE,
        'new_model_requests':0, 'outbound_sent':False, 'cases':[]}
    with httpx.Client(base_url=BASE, headers={'Origin':BASE}, timeout=60) as api:
        health = api.get('/api/health').raise_for_status().json()
        assert not any(health['channels'].values()), 'Do not run this check with outbound channels enabled'
        for episode in ['EP-2026-409', 'EP-2026-425', 'EP-2026-429']:
            state = api.post('/api/workflow/replay-scenario',json={'episode_id':episode}).raise_for_status().json()
            original_meds = state['medications']
            state = api.post('/api/workflow/rcs-action',json={'episode_id':episode,'option_id':'triage'}).raise_for_status().json()
            c = state['coordination']
            checks = []

            def check(condition, name):
                assert condition, name
                checks.append(name)

            def command(kind, key='', **extra):
                body = {'episode_id':episode,'run_id':c['run_id'],'event_id':uuid.uuid4().hex,'kind':kind}
                if key:
                    body.update(task_id=key,correlation_id=c['tasks'][key]['correlation_id'])
                body.update(extra)
                return body

            def send(body):
                nonlocal state, c
                state = api.post('/api/workflow/coordination-event',json=body).raise_for_status().json()
                c = state['coordination']
                return c

            check(c['tasks']['clinical_review']['owner']=='Synthetic treating clinical team','review_has_owner')
            if episode.endswith('409'):
                send(command('DELIVERED','patient_contact'))
                send(command('DELIVERY_FAILED','patient_contact'))
                check(c['last_event_result']['status']=='LATE_RECEIPT_IGNORED','contradictory_receipt_does_not_regress')
                send(command('ADVANCE_CLOCK',advance_seconds=180))
                check('caregiver_contact' in c['tasks'],'delivered_but_unacknowledged_contact_times_out')
            else:
                failure = command('DELIVERY_FAILED','patient_contact')
                send(failure)
                before = len(c['outbox'])
                send(failure)
                check(c['last_event_result']['status']=='DUPLICATE_IGNORED' and len(c['outbox'])==before,'duplicate_failure_has_one_fallback')
            if episode.endswith('425'):
                send(command('DELIVERY_FAILED','caregiver_contact'))
                check('manual_contact' in c['tasks'],'two_failed_paths_require_manual_contact')
                send(command('ADVANCE_CLOCK',advance_seconds=360))
                send(command('ADVANCE_CLOCK',advance_seconds=360))
                check(c['tasks']['manual_contact']['status']=='MANUAL_INTERVENTION','retry_limit_routes_to_duty_supervisor')
            reply = command('CONCERN_REPORTED','caregiver_contact',
                text='SYNTHETIC QA caregiver reply: concern persists; treating-team reassessment is still required.')
            bad = {**reply,'event_id':uuid.uuid4().hex,'correlation_id':'wrong-episode-and-run'}
            check(api.post('/api/workflow/coordination-event',json=bad).status_code==422,'cross_episode_correlation_rejected')
            send(reply)
            check(c['concern_open'] and 'reassessment' in c['tasks'],'caregiver_concern_attached_to_existing_case')
            send(reply)
            check(c['last_event_result']['status']=='DUPLICATE_IGNORED','duplicate_reply_does_not_create_another_task')
            check(api.post('/api/workflow/coordination-event',json={**reply,'text':'Different synthetic payload must not reuse the same event identity.'}).status_code==422,'event_id_payload_conflict_rejected')
            check(api.post('/api/workflow/coordination-event',json={**reply,'run_id':'stale-run'}).status_code==422,'old_run_event_rejected')
            send(command('ADVANCE_CLOCK',advance_seconds=360))
            check(c['tasks']['clinical_review']['status']=='ESCALATED' and 'on_call_review' in c['tasks'],'unanswered_review_escalates_owner')
            check(not state['clinical_review'] and not state['patient_acknowledgement'] and not state['follow_up_record'],'events_do_not_fabricate_human_care')
            check(state['medications']==original_meds,'written_medications_unchanged')
            check(all(item['status']=='PREVIEW_ONLY' for item in c['outbox']),'contact_intents_are_not_delivery_claims')
            check(state['audit']['mode']=='NOT_SENT','audit_not_emailed')
            check(api.get(state['audit']['pdf_url']).raise_for_status().content.startswith(b'%PDF'),'updated_handoff_pdf_available')
            # A separate read verifies the event ledger and ownership survived persistence.
            restored = api.get('/api/patients/'+episode).raise_for_status().json()['coordination']
            check(restored['processed_events']==c['processed_events'],'ledger_persisted_across_requests')
            if episode.endswith('425'):
                check(c['tasks']['manual_contact']['status']=='COMPLETED','late_reply_reconciles_manual_contact')
            report['cases'].append({'episode_id':episode,'passed':True,'checks':checks,
                'run_id':c['run_id'],'policy':c['policy'],'clock_offset_seconds':c['clock_offset_seconds']})
            print(f'{episode}: {len(checks)} coordination checks PASS',flush=True)
    report['checks_passed'] = sum(len(case['checks']) for case in report['cases'])
    (ROOT/'submission/coordination-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Public coordination validation PASS; no model calls or outbound sends')


if __name__ == '__main__':
    main()
