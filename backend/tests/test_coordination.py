import copy

import pytest
from agentcore.coordination import apply_event, open_coordination, tick
from models.schemas import CoordinationCommand, PatientState


@pytest.fixture
def state():
    value = PatientState(episode_id='EP-2026-409', patient_id='synthetic', name='Synthetic test', age=58,
        condition='Synthetic pathway', day=1, phone='+15550000001', caregiver_phone='+15550000002',
        physician_email='synthetic@example.org', order={'status':'PENDING_CLINICIAN_REVIEW'})
    open_coordination(value, at=1000)
    return value


def event(state, kind, task='patient_contact', event_id='event-0001', **kwargs):
    c = state.coordination
    return CoordinationCommand(episode_id=state.episode_id, run_id=c['run_id'], event_id=event_id,
        kind=kind, task_id=task, correlation_id=c['tasks'][task]['correlation_id'], **kwargs)


def test_deadline_autonomously_adapts_and_escalates_once(state):
    tick(state, at=1301)
    c = state.coordination
    assert c['tasks']['patient_contact']['status'] == 'SUPERSEDED'
    assert c['tasks']['clinical_review']['status'] == 'ESCALATED'
    assert c['tasks']['on_call_review']['owner'] == 'Synthetic on-call clinician'
    assert len(c['outbox']) == 2
    before = copy.deepcopy(c)
    assert not tick(state, at=1301)
    assert c == before
    assert state.clinical_review is None and state.patient_acknowledgement is None


def test_duplicate_failure_does_not_duplicate_fallback(state):
    command = event(state, 'DELIVERY_FAILED')
    apply_event(state, command, at=1000)
    apply_event(state, command, at=1000)
    assert state.coordination['last_event_result']['status'] == 'DUPLICATE_IGNORED'
    assert len(state.coordination['outbox']) == 2
    assert len(state.coordination['processed_events']) == 1


def test_reused_event_id_with_changed_payload_rejected(state):
    apply_event(state, event(state, 'DELIVERY_FAILED'))
    with pytest.raises(ValueError, match='different payload'):
        apply_event(state, event(state, 'DELIVERED'))


def test_stale_run_and_cross_episode_correlation_rejected(state):
    command = event(state, 'DELIVERY_FAILED')
    with pytest.raises(ValueError, match='Stale'):
        apply_event(state, command.model_copy(update={'run_id':'other-run'}))
    with pytest.raises(ValueError, match='correlate'):
        apply_event(state, command.model_copy(update={'correlation_id':'other-episode:patient_contact'}))


def test_late_receipt_does_not_restore_failed_channel(state):
    apply_event(state, event(state, 'DELIVERY_FAILED'))
    apply_event(state, event(state, 'DELIVERED', event_id='event-0002'))
    c = state.coordination
    assert c['last_event_result']['status'] == 'LATE_RECEIPT_IGNORED'
    assert c['tasks']['patient_contact']['status'] == 'SUPERSEDED'


def test_failed_receipt_after_delivery_does_not_regress(state):
    apply_event(state, event(state, 'DELIVERED'))
    apply_event(state, event(state, 'DELIVERY_FAILED', event_id='event-0002'))
    assert state.coordination['last_event_result']['status'] == 'LATE_RECEIPT_IGNORED'
    assert 'caregiver_contact' not in state.coordination['tasks']
    # Delivery still does not prove acknowledgment. Timeout may adapt the path.
    tick(state, at=1121)
    assert 'caregiver_contact' in state.coordination['tasks']


def test_provider_failures_are_bounded_and_remain_unresolved(state):
    apply_event(state, event(state, 'DELIVERY_FAILED'))
    apply_event(state, event(state, 'DELIVERY_FAILED', 'caregiver_contact', 'event-0002'))
    tick(state, at=1181)
    tick(state, at=1362)
    item = state.coordination['tasks']['manual_contact']
    assert item['status'] == 'MANUAL_INTERVENTION' and item['attempts'] == 2
    tick(state, at=9999)
    assert item['attempts'] == 2
    assert state.follow_up_record is None


def test_correlated_caregiver_concern_never_auto_completes_care(state):
    apply_event(state, event(state, 'DELIVERY_FAILED'))
    reply = event(state, 'CONCERN_REPORTED', 'caregiver_contact', 'event-0002',
        text='SYNTHETIC caregiver: concern persists; please reassess.')
    apply_event(state, reply)
    apply_event(state, reply)
    c = state.coordination
    assert c['concern_open'] and c['tasks']['reassessment']['status'] == 'OPEN'
    assert len([t for t in c['tasks'] if t == 'reassessment']) == 1
    assert state.order == {'status':'PENDING_CLINICIAN_REVIEW'}
    assert state.clinical_review is None and state.patient_acknowledgement is None
    assert state.medications == []


def test_late_reply_reconciles_manual_contact_without_erasing_concern(state):
    tick(state, at=1121)
    tick(state, at=1302)
    apply_event(state, event(state, 'CONCERN_REPORTED', 'caregiver_contact',
        text='SYNTHETIC late reply: symptoms remain unresolved.'))
    assert state.coordination['tasks']['manual_contact']['status'] == 'COMPLETED'
    assert state.coordination['concern_open']


def test_clinician_decision_reconciles_escalation_but_requires_teachback(state):
    tick(state, at=1301)
    state.clinical_review = {'decision':'CLINICIAN_CONTACT'}
    tick(state, at=1302)
    c = state.coordination
    assert c['tasks']['on_call_review']['status'] == 'COMPLETED'
    assert c['tasks']['teach_back']['status'] == 'OPEN'
    assert 'follow_up' not in c['tasks']
    state.patient_acknowledgement = {'teach_back':'synthetic response'}
    tick(state, at=1303)
    assert c['tasks']['teach_back']['status'] == 'COMPLETED'
    assert c['tasks']['follow_up']['status'] == 'OPEN'
    state.follow_up_record = {'outcome':'REASSESSMENT_REQUESTED'}
    tick(state, at=1304)
    assert c['tasks']['follow_up']['status'] == 'COMPLETED' and c['concern_open']


def test_clock_cap_and_duplicate_clock_event(state):
    command = CoordinationCommand(episode_id=state.episode_id,run_id=state.coordination['run_id'],
        event_id='clock-0001', kind='ADVANCE_CLOCK',advance_seconds=900)
    apply_event(state, command, at=1000)
    apply_event(state, command, at=1000)
    assert state.coordination['clock_offset_seconds'] == 900
    for n in range(2,5):
        apply_event(state, command.model_copy(update={'event_id':f'clock-000{n}'}), at=1000)
    with pytest.raises(ValueError, match='one synthetic hour'):
        apply_event(state, command.model_copy(update={'event_id':'clock-0005'}), at=1000)


def test_events_and_outbox_survive_state_roundtrip(state):
    command = event(state, 'DELIVERY_FAILED')
    apply_event(state, command)
    restored = PatientState.model_validate_json(state.model_dump_json())
    apply_event(restored, command)
    assert restored.coordination['last_event_result']['status'] == 'DUPLICATE_IGNORED'
    assert len(restored.coordination['outbox']) == 2
