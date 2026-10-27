"""Bounded, deterministic coordination policy. Synthetic operational deadlines, not triage.

No model calls or provider sends. Tasks/outbox are persisted together with episode state.
The hosted scheduler and interactive event injector run this same reducer under a DDB lease.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

POLICY = 'synthetic-handoff-v1'


def utc_seconds():
    return int(datetime.now(timezone.utc).timestamp())


def log(c, action, reason, task_id='', at=None):
    c['decisions'].append({'at': at if at is not None else c['logical_now'],
        'action': action, 'reason': reason, 'task_id': task_id, 'policy': POLICY})
    c['decisions'] = c['decisions'][-80:]


def task(c, key, owner, seconds, reason, contact=False):
    if key in c['tasks']:
        return
    entry = {'id':key, 'owner':owner, 'status':'OPEN', 'due_at':c['logical_now']+seconds,
        'reason':reason, 'delivery':'NOT_SENT' if contact else 'NOT_APPLICABLE',
        'correlation_id':f'{c["run_id"]}:{key}', 'attempts':0}
    c['tasks'][key] = entry
    if contact:
        # A durable intent, not an external transmission or delivery receipt.
        c['outbox'].append({'id':entry['correlation_id'], 'task_id':key, 'audience':owner,
            'status':'PREVIEW_ONLY', 'episode_id':c['episode_id'],
            'text':'SYNTHETIC: clinical review is pending. Reply with context; no medication change is authorized.'})
    log(c, 'TASK_CREATED', reason, key)


def open_coordination(state, at=None):
    if state.coordination:
        return
    at = utc_seconds() if at is None else at
    c = {'run_id':uuid.uuid4().hex, 'episode_id':state.episode_id, 'policy':POLICY,
        'mode':'SYNTHETIC_POLICY', 'clock_offset_seconds':0, 'logical_now':at,
        'started_at':at, 'tasks':{}, 'outbox':[], 'decisions':[], 'processed_events':{},
        'last_event_result':None, 'concern_open':False, 'scheduler_last_checked_at':None}
    state.coordination = c
    task(c, 'clinical_review', 'Synthetic treating clinical team', 300,
        'Analyzed evidence requires an accountable human review.')
    task(c, 'patient_contact', 'Synthetic patient', 120,
        'A delivered message is not assumed; await correlated contact evidence.', True)
    log(c, 'POLICY_STARTED', 'Operational demo timers only; never wait for these timers in a real emergency.')


def complete(c, key, reason):
    item = c['tasks'].get(key)
    if item and item['status'] not in ('COMPLETED', 'SUPERSEDED'):
        item['status'] = 'COMPLETED'
        log(c, 'TASK_COMPLETED', reason, key)


def synchronize(state):
    c = state.coordination
    if state.clinical_review:
        complete(c, 'clinical_review', 'Explicit synthetic clinician decision recorded; not inferred from a message.')
        complete(c, 'on_call_review', 'Original review received; duplicate review task reconciled.')
        if not state.patient_acknowledgement:
            task(c, 'teach_back', 'Synthetic care coordinator', 180,
                'Human-reviewed plan requires patient/caregiver teach-back.')
    if state.patient_acknowledgement:
        complete(c, 'teach_back', 'Teach-back explicitly recorded; understanding is not automatically verified.')
        complete(c, 'patient_contact', 'Explicit plan acknowledgment reconciles contact tracking.')
        complete(c, 'caregiver_contact', 'Explicit plan acknowledgment reconciles contact tracking.')
        complete(c, 'manual_contact', 'Explicit plan acknowledgment reconciles contact tracking.')
        if not state.follow_up_record:
            task(c, 'follow_up', 'Synthetic discharge coordinator', 300,
                'A contact outcome must be recorded separately from acknowledgment.')
    if state.follow_up_record:
        complete(c, 'follow_up', 'Synthetic follow-up outcome recorded; recovery not established.')
        if state.follow_up_record['outcome'] == 'REASSESSMENT_REQUESTED':
            c['concern_open'] = True
            task(c, 'reassessment', 'Synthetic on-call clinician', 300,
                'Persistent concern remains open despite a recorded follow-up.')


def contact_failed(c, key, reason):
    item = c['tasks'][key]
    if item['status'] in ('COMPLETED', 'SUPERSEDED'):
        return
    item['status'] = 'SUPERSEDED'
    item['delivery'] = 'SIMULATED_FAILED'
    log(c, 'CHANNEL_ADAPTED', reason, key)
    if key == 'patient_contact':
        task(c, 'caregiver_contact', 'Synthetic caregiver', 180,
            'Patient contact failed or timed out; preserve the same episode in the caregiver intent.', True)
    elif key == 'caregiver_contact':
        task(c, 'manual_contact', 'Synthetic care coordinator', 180,
            'Both automated contact paths are unconfirmed; require manual contact. No delivery is fabricated.')


def tick(state, at=None):
    c = state.coordination
    if not c:
        return False
    before = json.dumps(c, sort_keys=True)
    real_now = utc_seconds() if at is None else at
    c['logical_now'] = max(c['logical_now'], real_now+c['clock_offset_seconds'])
    synchronize(state)
    # Only existing tasks are evaluated once per tick: a large clock jump cannot
    # skip directly past a newly created escalation's own response window.
    for key, item in list(c['tasks'].items()):
        if item['status'] != 'OPEN' or item['due_at'] > c['logical_now']:
            continue
        if key in ('patient_contact', 'caregiver_contact'):
            contact_failed(c, key, 'No correlated response before the synthetic operational deadline.')
        elif key == 'clinical_review':
            item['status'] = 'ESCALATED'
            task(c, 'on_call_review', 'Synthetic on-call clinician', 300,
                'Treating-team review deadline elapsed; ownership escalated without making a clinical decision.')
            log(c, 'OWNER_ESCALATED', 'Review unanswered; on-call task created once.', key)
        else:
            # Bounded retries are durable task intents, never fake provider sends.
            item['attempts'] += 1
            if item['attempts'] < 2:
                item['due_at'] = c['logical_now']+180
                log(c, 'TASK_RETRY', 'First operational retry; no model call or outbound transmission.', key)
            else:
                item['status'] = 'MANUAL_INTERVENTION'
                item['owner'] = 'Synthetic duty supervisor'
                log(c, 'MANUAL_INTERVENTION', 'Retry limit reached; unresolved work stays visible to the duty supervisor.', key)
    return before != json.dumps(c, sort_keys=True)


def apply_event(state, command, at=None):
    c = state.coordination
    if not c or c['run_id'] != command.run_id or state.episode_id != command.episode_id:
        raise ValueError('Stale or unknown coordination run. Reload the current handoff.')
    payload = command.model_dump()
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = c['processed_events'].get(command.event_id)
    if previous:
        if previous['fingerprint'] != fingerprint:
            raise ValueError('Event ID was already used with a different payload.')
        c['last_event_result'] = {'event_id':command.event_id, 'status':'DUPLICATE_IGNORED'}
        return
    if len(c['processed_events']) >= 100:
        raise ValueError('Synthetic run event limit reached; replay the case to start a new run.')
    if command.kind == 'ADVANCE_CLOCK':
        if not 1 <= command.advance_seconds <= 900 or c['clock_offset_seconds']+command.advance_seconds > 3600:
            raise ValueError('Advance 1–900 seconds per action, at most one synthetic hour per run.')
        c['clock_offset_seconds'] += command.advance_seconds
        tick(state, at)
        log(c, 'CLOCK_ADVANCED', f'Synthetic operational clock advanced by {command.advance_seconds}s. Real clinical urgency is not simulated by this timer.')
        result = 'APPLIED'
    else:
        item = c['tasks'].get(command.task_id)
        if not item or command.correlation_id != item['correlation_id'] or command.task_id not in ('patient_contact', 'caregiver_contact'):
            raise ValueError('Reply/receipt must correlate to a contact intent in this episode and run.')
        if command.kind in ('CAREGIVER_REPLY', 'CONCERN_REPORTED') and command.task_id != 'caregiver_contact':
            raise ValueError('Caregiver responses must correlate to the caregiver contact intent.')
        if command.kind in ('CAREGIVER_REPLY', 'CONCERN_REPORTED') and len(command.text.strip()) < 10:
            raise ValueError('A synthetic caregiver response must contain at least 10 characters.')
        if command.kind in ('DELIVERED', 'DELIVERY_FAILED') and (item['status'] != 'OPEN'
                or (command.kind == 'DELIVERY_FAILED' and item['delivery'] == 'SIMULATED_DELIVERED')):
            result = 'LATE_RECEIPT_IGNORED'
            log(c, result, 'A delayed receipt cannot reopen or regress a completed/superseded contact.', command.task_id)
        elif command.kind == 'DELIVERY_FAILED':
            contact_failed(c, command.task_id, 'Correlated simulated provider failure; selected next permitted contact path.')
            result = 'APPLIED'
        elif command.kind == 'DELIVERED':
            item['delivery'] = 'SIMULATED_DELIVERED'
            log(c, 'RECEIPT_RECORDED', 'Simulated delivery is not acknowledgment, clinical assessment or recovery.', command.task_id)
            result = 'APPLIED'
        else:
            complete(c, command.task_id, 'Correlated synthetic caregiver response; human interpretation still required.')
            complete(c, 'manual_contact', 'Late caregiver response reconciles the pending manual-contact task.')
            c['last_caregiver_reply'] = {'text':command.text, 'event_id':command.event_id,
                'correlation_id':command.correlation_id, 'at':c['logical_now'], 'simulation':True}
            if command.kind == 'CONCERN_REPORTED':
                c['concern_open'] = True
                task(c, 'reassessment', 'Synthetic on-call clinician', 300,
                    'Caregiver explicitly reports persistent concern; request human reassessment, never infer recovery.')
            log(c, 'CONTEXT_ATTACHED', 'Reply attached to the existing episode; no duplicate clinical request, no automatic teach-back verification.', command.task_id)
            result = 'APPLIED'
    c['processed_events'][command.event_id] = {'fingerprint':fingerprint, 'result':result}
    c['last_event_result'] = {'event_id':command.event_id, 'status':result}
