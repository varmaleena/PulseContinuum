import json
from unittest.mock import Mock

import pytest
from agentcore import demo_email
from botocore.exceptions import ClientError
from config import settings
from models.schemas import DemoEmailRequest, PatientState


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    cfg = settings()
    for key, value in {'aws_mode':'live','demo_email_enabled':True,'memory_table':'synthetic-table',
        'demo_email_recipient':'approved@example.org','ses_verified_sender':'approved@example.org'}.items():
        monkeypatch.setattr(cfg,key,value)
    pdf = tmp_path/'packet.pdf'
    pdf.write_bytes(b'%PDF-synthetic-test')
    monkeypatch.setattr(demo_email,'load_artifact',lambda key:pdf)
    db, ses = Mock(), Mock()
    ses.send_email.return_value = {'MessageId':'ses-test-id','ResponseMetadata':{'RequestId':'ses-request','HTTPStatusCode':200}}
    monkeypatch.setattr(demo_email,'client',lambda service:db if service=='dynamodb' else ses)
    state = PatientState(episode_id='EP-2026-409',patient_id='test',name='Synthetic',age=58,
        condition='Test',day=1,phone='',caregiver_phone='',physician_email='not-the-destination@example.org',
        audit={'sha256':'abc123','html':'<p>Synthetic report</p>','artifact_key':'versioned.pdf'})
    return state,db,ses


def test_email_fixed_recipient_and_real_acceptance_metadata(prepared):
    state,db,ses = prepared
    receipt = demo_email.send_packet(state)
    assert receipt['status']=='ACCEPTED_BY_SES' and not receipt['inbox_delivery_verified']
    assert ses.send_email.call_args.kwargs['Destination']=={'ToAddresses':['approved@example.org']}
    assert b'SYNTHETIC' in ses.send_email.call_args.kwargs['Content']['Raw']['Data']
    transaction = db.transact_write_items.call_args.kwargs['TransactItems']
    assert transaction[0]['Update']['ExpressionAttributeValues'][':limit']=={'N':'3'}
    assert 'attribute_not_exists' in transaction[1]['Put']['ConditionExpression']


def cancelled():
    return ClientError({'Error':{'Code':'TransactionCanceledException','Message':'synthetic condition'}},'TransactWriteItems')


def test_duplicate_email_returns_persisted_receipt_without_sending(prepared):
    state,db,ses = prepared
    db.transact_write_items.side_effect = cancelled()
    saved = {'status':'ACCEPTED_BY_SES','packet_sha256':'earlier-version'}
    db.get_item.return_value = {'Item':{'State':{'S':json.dumps(saved)}}}
    assert demo_email.send_packet(state)==saved
    ses.send_email.assert_not_called()


def test_daily_email_cap_blocks_before_ses(prepared):
    state,db,ses = prepared
    db.transact_write_items.side_effect = cancelled()
    db.get_item.return_value = {}
    with pytest.raises(ValueError,match='three email attempts'):
        demo_email.send_packet(state)
    ses.send_email.assert_not_called()


def test_uncertain_provider_outcome_is_persisted_not_retried(prepared):
    state,db,ses = prepared
    ses.send_email.side_effect = TimeoutError('Synthetic lost response')
    receipt = demo_email.send_packet(state)
    assert receipt['status']=='OUTCOME_UNKNOWN'
    ses.send_email.assert_called_once()
    assert 'OUTCOME_UNKNOWN' in db.update_item.call_args.kwargs['ExpressionAttributeValues'][':s']['S']


def test_non_synthetic_or_disabled_email_fails_closed(prepared,monkeypatch):
    state,db,ses = prepared
    state.is_synthetic = False
    with pytest.raises(ValueError,match='synthetic handoff'):
        demo_email.send_packet(state)
    state.is_synthetic = True
    monkeypatch.setattr(settings(),'demo_email_enabled',False)
    with pytest.raises(ValueError,match='not enabled'):
        demo_email.send_packet(state)
    db.transact_write_items.assert_not_called()
    ses.send_email.assert_not_called()


def test_caller_cannot_supply_an_email_destination():
    with pytest.raises(ValueError):
        DemoEmailRequest.model_validate({'episode_id':'EP-2026-409','recipient':'arbitrary@example.org'})


def test_missing_attachment_does_not_consume_allowance(prepared,monkeypatch):
    state,db,ses = prepared
    monkeypatch.setattr(demo_email,'load_artifact',lambda key:None)
    with pytest.raises(ValueError,match='attachment'):
        demo_email.send_packet(state)
    db.transact_write_items.assert_not_called()
    ses.send_email.assert_not_called()


@pytest.mark.parametrize('http_status,expected',[(403,'REJECTED_BY_SES'),(500,'OUTCOME_UNKNOWN')])
def test_definitive_rejection_is_distinguished_from_uncertain_server_error(prepared,http_status,expected):
    state,db,ses = prepared
    ses.send_email.side_effect = ClientError({'Error':{'Code':'AccessDeniedException' if http_status==403 else 'InternalServiceError'},
        'ResponseMetadata':{'HTTPStatusCode':http_status}},'SendEmail')
    result = demo_email.send_packet(state)
    assert result['status']==expected and result['error_code']
    ses.send_email.assert_called_once()
