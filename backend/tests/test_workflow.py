import hashlib
import hmac
import io

import pytest
from agentcore.guardrails import verify_medications
from agentcore.memory_graph import MemoryGraph
from config import settings
from fastapi.testclient import TestClient
from main import app, supervisor
from telemetry import telemetry


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings(), 'data_dir', str(tmp_path))
    monkeypatch.setattr(settings(), 'aws_mode', 'demo')
    monkeypatch.setattr(settings(), 'api_token', '')
    supervisor.memory = MemoryGraph()
    supervisor.timeouts = {}
    supervisor.locks = {}
    telemetry.events.clear()
    with TestClient(app) as test_client:
        yield test_client


def test_full_clinical_loop_and_idempotency(client):
    episode = 'EP-2026-409'
    assert len(client.get('/api/patients').json()) == 6
    assert client.post('/api/workflow/whatsapp-multimodal').status_code == 422
    response = client.post('/api/workflow/ingest-discharge', data={'episode_id': episode})
    assert response.status_code == 200, response.text
    assert len(response.json()['medications']) == 2
    response = client.post('/api/workflow/whatsapp-multimodal', data={'episode_id': episode,
        'transcript': 'I took the blue tablet and now have a 101.2F fever and dizziness'})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['risk_score'] >= 82
    assert state['analysis']['guardrail_verification']['status'] == 'REVIEW_REQUIRED'
    assert len(state['rcs_cards']) == 3
    state = client.post('/api/workflow/simulate-deadzone-failover', json={'episode_id': episode}).json()
    sms = [m for m in state['messages'] if m['channel'] == 'SMS']
    assert len(sms) == 2
    assert sms[0]['destination'] != sms[1]['destination']
    repeated = client.post('/api/workflow/simulate-deadzone-failover', json={'episode_id': episode}).json()
    assert len(repeated['messages']) == len(state['messages'])
    state = client.post('/api/workflow/caregiver-sms-reply', json={'episode_id': episode, 'reply': '1'}).json()
    assert state['order']['status'] == 'PENDING_CLINICIAN_APPROVAL'
    assert state['audit']['mode'] == 'DEMO'
    audit = state['audit']
    assert hashlib.sha256(audit['canonical_payload'].encode()).hexdigest() == audit['sha256']
    assert hmac.new(settings().audit_signing_key.encode(), audit['canonical_payload'].encode(), hashlib.sha256).hexdigest() == audit['hmac_sha256']
    pdf = client.get(audit['pdf_url'])
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    from pypdf import PdfReader
    assert 'Clinician review required' in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    repeated = client.post('/api/workflow/caregiver-sms-reply', json={'episode_id': episode}).json()
    assert repeated['order']['order_id'] == state['order']['order_id']
    assert len([e for e in client.get('/api/telemetry').json() if e.get('category') == 'SES_V2']) == 1
    assert MemoryGraph().get(episode).order is not None
    logs = client.get('/api/telemetry').json()
    sdk_logs = [e for e in logs if 'execution_mode' in e and e['category'] != 'MCP_PHARMACY']
    assert all(e['request_id'] is None and e['http_status'] is None for e in sdk_logs)
    assert client.post('/api/workflow/caregiver-sms-reply', json={'reply': '9'}).status_code == 422
    assert client.get('/api/patients/unknown').status_code == 404


def test_websocket_and_upload_validation(client):
    with client.websocket_connect('/ws/events') as ws:
        telemetry.emit({'category': 'TEST'})
        assert ws.receive_json()['category'] == 'TEST'
    assert client.post('/api/workflow/ingest-discharge', files={'file': ('bad.pdf', b'bad', 'application/pdf')}).status_code == 422
    client.post('/api/workflow/ingest-discharge')
    assert client.post('/api/workflow/whatsapp-multimodal', files={'image': ('bad.jpg', b'bad', 'image/jpeg')}).status_code == 422
    assert client.post('/api/webhooks/delivery', json={'message_id':'x','status':'FAILED','event_id':'x'}).status_code == 401


def test_dosage_gate_requires_readable_exact_strength():
    permitted = [{'name':'Pantoprazole','strength':'40mg'}]
    assert not verify_medications([{'name':'Pantoprazole','strength':'400mg','label_readable':True}], permitted)['dosage_verified']
    assert not verify_medications([{'name':'Pantoprazole','strength':'40mg','label_readable':False}], permitted)['dosage_verified']
    assert verify_medications([{'name':'Pantoprazole','strength':'40mg','label_readable':True}], permitted)['dosage_verified']


def test_rcs_action_and_delivery_receipt(client, monkeypatch):
    monkeypatch.setattr(settings(), 'webhook_token', 'test-secret')
    client.post('/api/workflow/ingest-discharge')
    state = client.post('/api/workflow/whatsapp-multimodal').json()
    message_id = state['pending_message_id']
    response = client.post('/api/webhooks/delivery', json={'episode_id':state['episode_id'],
        'message_id':message_id,'status':'DELIVERED','event_id':'delivered-1'}, headers={'x-webhook-token':'test-secret'})
    assert response.status_code == 200
    assert response.json()['delivery_status'] == 'DELIVERED'
    stale = client.post('/api/webhooks/delivery', json={'episode_id':state['episode_id'],
        'message_id':'old-message','status':'FAILED','event_id':'old'}, headers={'x-webhook-token':'test-secret'})
    assert not stale.json()['blackout']
    response = client.post('/api/workflow/rcs-action', json={'option_id':'triage'})
    assert response.status_code == 200
    assert response.json()['order']['option']['id'] == 'triage'


def test_aws_adapter_payloads_with_botocore_stubber(monkeypatch):
    import aws_client
    import boto3
    from botocore.stub import Stubber
    from mcp_gateway.cds_dispatcher_mcp import AWSCDSEngine
    monkeypatch.setattr(settings(), 'aws_mode', 'live')
    monkeypatch.setattr(settings(), 'rcs_origination_id', 'rcs-agent-test')
    monkeypatch.setattr(settings(), 'outbound_channels', 'RCS')
    sdk = boto3.client('pinpoint-sms-voice-v2', region_name='us-east-1',
                       aws_access_key_id='test', aws_secret_access_key='test')
    stub = Stubber(sdk)
    stub.add_response('send_rcs_message', {'MessageId':'real-stub-id','ResponseMetadata':{'RequestId':'stub-request','HTTPStatusCode':200}})
    monkeypatch.setattr(aws_client, 'client', lambda service: sdk)
    with stub:
        result = AWSCDSEngine().send_rcs_pharmacy_carousel('+12025550409','Rajesh',[
            {'title':'Pharmacy','copay':'$0','eta':'35 min','action':'Request','id':'generic'},
            {'title':'Triage','copay':'$0','eta':'4 PM','action':'Book','id':'triage'}])
    assert result['execution_mode'] == 'LIVE_AWS'
    assert result['request_id'] == 'stub-request'


def test_timeout_watchdog(client):
    import asyncio
    from unittest.mock import AsyncMock

    from agentcore.supervisor import Supervisor
    instance = Supervisor()
    state = instance.memory.get('EP-2026-409')
    state.delivery_status = 'PENDING'
    state.pending_message_id = 'pending'
    instance.memory.save(state)
    instance.failover = AsyncMock()
    async def exercise():
        from unittest.mock import patch
        real_sleep = asyncio.sleep
        with patch('agentcore.supervisor.asyncio.sleep', new=AsyncMock()):
            instance.arm_timeout(state.episode_id, 'pending')
            await real_sleep(0)
            await instance.timeouts[state.episode_id]
        instance.failover.assert_awaited_once_with(state.episode_id, 'TIMEOUT', 'pending')
    asyncio.run(exercise())


def test_native_ingress_and_unknown_envelopes(client):
    import asyncio
    from unittest.mock import AsyncMock, Mock

    from agentcore.inbound_worker import process_event
    fake = Mock()
    fake.memory.resolve.return_value = 'EP-2026-409'
    fake.fulfill = AsyncMock()
    fake.multimodal = AsyncMock()
    fake.failover = AsyncMock()
    asyncio.run(process_event(fake, {'originationNumber': '+12025551409', 'messageBody': '1'}))
    fake.fulfill.assert_awaited_once_with('EP-2026-409', reply='1')
    asyncio.run(process_event(fake, {'detail': {'episode_id':'EP-2026-409','status':'TIMEOUT','message_id':'pending'}}))
    fake.failover.assert_awaited_once_with('EP-2026-409', 'TIMEOUT', 'pending')
    with pytest.raises(ValueError, match='Unsupported inbound envelope'):
        asyncio.run(process_event(fake, {'unexpected': 'payload'}))


def test_malformed_bedrock_response_fails_closed(client, monkeypatch):
    import agentcore.vision_forensics as vision
    monkeypatch.setattr(vision, 'call', lambda *args, **kwargs: {'execution_mode':'LIVE_AWS',
        'response':{'output':{'message':{'content':[{'text':'{"identified_medications":["bad"],"clinical_red_flags":[],"readmission_risk_score":999,"summary":"unsafe"}'}]}}}})
    state = {'medications': [{'name':'Pantoprazole','strength':'40mg'}]}
    result = vision.analyze_patient_submission(None, 'fever', state)
    assert not result['guardrail_verification']['dosage_verified']
    assert result['readmission_risk_score'] == 82
    assert result['clinical_red_flags']


def test_live_disabled_channel_never_fakes_delivery(client, monkeypatch):
    from mcp_gateway.cds_dispatcher_mcp import AWSCDSEngine
    monkeypatch.setattr(settings(), 'aws_mode', 'live')
    monkeypatch.setattr(settings(), 'outbound_channels', '')
    result = AWSCDSEngine().send_whatsapp_clinical_message('+12025550409', 'Synthetic connectivity test')
    assert result['execution_mode'] == 'NOT_SENT'
    assert result['message_id'] is None
    assert result['request_id'] is None


def test_live_email_recipient_allowlist(client, monkeypatch):
    from mcp_gateway.cds_dispatcher_mcp import AWSCDSEngine
    monkeypatch.setattr(settings(), 'aws_mode', 'live')
    monkeypatch.setattr(settings(), 'outbound_channels', 'SES')
    monkeypatch.setattr(settings(), 'allowed_email_recipients', 'approved@example.org')
    result = AWSCDSEngine().send_ses_clinical_escalation_email('unapproved@example.org', 'Test', '<p>Test</p>')
    assert result['execution_mode'] == 'NOT_SENT'
    assert 'allowlist' in result['error']


def test_synthetic_cohort_and_case_specific_discharge(client):
    patients = client.get('/api/patients').json()
    assert len(patients) == 6
    assert len({patient['phone'] for patient in patients}) == 6
    assert all(patient['is_synthetic'] and patient['profile']['dataset_id'] == 'PULSE-SYNTH-2026-10' for patient in patients)
    assert all(patient['phone'].startswith('+120255501') for patient in patients)
    assert len({patient['condition'] for patient in patients}) == 6
    state = client.post('/api/workflow/ingest-discharge', data={'episode_id':'EP-2026-412'}).json()
    assert {med['name'] for med in state['medications']} == {'Aspirin', 'Atorvastatin'}
    assert client.get('/api/fixtures/EP-2026-412/discharge.pdf').content.startswith(b'%PDF')


def test_clinical_evidence_normalizes_one_flag():
    from agentcore.vision_forensics import ClinicalEvidence
    evidence = ClinicalEvidence.model_validate({'identified_medications': [],
        'clinical_red_flags': 'Reported symptom requires review', 'readmission_risk_score': 30, 'summary': 'Review'})
    assert evidence.clinical_red_flags == ['Reported symptom requires review']


def test_hosted_artifact_recovers_after_cache_loss(client, monkeypatch):
    from unittest.mock import Mock

    import artifact_store
    monkeypatch.setattr(settings(), 'serverless', True)
    monkeypatch.setattr(settings(), 'assets_bucket', 'synthetic-assets')
    upload = Mock()
    monkeypatch.setattr(artifact_store, 'call', upload)
    data = b'%PDF synthetic audit fixture'
    path = artifact_store.save_artifact('EP-2026-409-audit.pdf', data, 'application/pdf')
    assert upload.call_args.args[2]['Key'] == 'artifacts/EP-2026-409-audit.pdf'
    path.unlink()
    remote = Mock()
    remote.get_object.return_value = {'Body':io.BytesIO(data)}
    monkeypatch.setattr(artifact_store, 'client', lambda service: remote)
    restored = artifact_store.load_artifact('EP-2026-409-audit.pdf')
    assert restored.read_bytes() == data


def test_hosted_inference_allowance_fails_closed(client, monkeypatch):
    from unittest.mock import Mock

    import aws_client
    from botocore.exceptions import ClientError
    monkeypatch.setattr(settings(), 'aws_mode', 'live')
    monkeypatch.setattr(settings(), 'allow_demo_fallback', False)
    monkeypatch.setattr(settings(), 'max_model_calls_per_day', 1)
    database, model = Mock(), Mock()
    database.update_item.side_effect = ClientError({'Error':{'Code':'ConditionalCheckFailedException',
        'Message':'Daily synthetic demo inference allowance exhausted'}}, 'UpdateItem')
    monkeypatch.setattr(aws_client, 'client', lambda service: database if service == 'dynamodb' else model)
    with pytest.raises(RuntimeError, match='allowance exhausted'):
        aws_client.call('bedrock-runtime', 'converse', {}, 'BEDROCK_VISION')
    model.converse.assert_not_called()
