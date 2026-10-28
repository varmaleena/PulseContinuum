"""Explicit SES send to one server-configured verified inbox. Never auto-retry uncertain sends."""
import json
import time
from datetime import datetime, timezone
from email.message import EmailMessage

from artifact_store import load_artifact
from aws_client import client
from botocore.exceptions import ClientError
from config import settings
from telemetry import now, telemetry


def send_packet(state):
    cfg = settings()
    if not cfg.demo_email_enabled or cfg.aws_mode != 'live' or not cfg.memory_table:
        raise ValueError('Live synthetic demo email is not enabled.')
    if not state.is_synthetic or not state.audit or not cfg.demo_email_recipient or not cfg.ses_verified_sender:
        raise ValueError('A synthetic handoff packet and a verified fixed inbox are required.')
    path = load_artifact(state.audit.get('artifact_key') or f'{state.episode_id}-audit.pdf')
    if path is None:
        raise ValueError('The committed handoff attachment is not available.')
    # Prepare before reserving. The fixed destination is never accepted from an HTTP caller.
    mime = EmailMessage()
    mime['Subject'] = f'[SYNTHETIC DEMO] PulseContinuum handoff | {state.episode_id}'
    mime['From'] = cfg.ses_verified_sender
    mime['To'] = cfg.demo_email_recipient
    mime.set_content('SYNTHETIC HACKATHON DEMO. No real patient, prescription, consultation or emergency request.\n'
        f'Episode: {state.episode_id}\nPacket SHA-256: {state.audit["sha256"]}\nSee the attached handoff PDF.')
    mime.add_alternative('<p>SYNTHETIC HACKATHON DEMO — no real clinical request.</p>'+state.audit['html'],subtype='html')
    mime.add_attachment(path.read_bytes(),maintype='application',subtype='pdf',filename='synthetic-care-handoff.pdf')
    payload = mime.as_bytes()
    db = client('dynamodb')
    day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    key = {'EpisodeID':{'S':'EMAIL#'+day},'EntityKey':{'S':state.episode_id}}
    receipt = {'status':'PENDING','recorded_at':now(),'packet_sha256':state.audit['sha256'],
        'destination':'Owner verified demo inbox','synthetic':True,'inbox_delivery_verified':False,
        'note':'SES acceptance is not proof of inbox delivery.'}
    try:
        db.transact_write_items(TransactItems=[{'Update':{'TableName':cfg.memory_table,
            'Key':{'EpisodeID':{'S':'BUDGET#'+day},'EntityKey':{'S':'SES_DEMO'}},
            'UpdateExpression':'ADD SendAttempts :one',
            'ConditionExpression':'attribute_not_exists(SendAttempts) OR SendAttempts < :limit',
            'ExpressionAttributeValues':{':one':{'N':'1'},':limit':{'N':'3'}}}},
            {'Put':{'TableName':cfg.memory_table,'Item':{**key,'State':{'S':json.dumps(receipt)},
                'ExpiresAt':{'N':str(int(time.time())+30*86400)}},
                'ConditionExpression':'attribute_not_exists(EpisodeID)'}}])
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'TransactionCanceledException':
            raise
        previous = db.get_item(TableName=cfg.memory_table,Key=key,ConsistentRead=True).get('Item')
        if previous:
            stored = json.loads(previous['State']['S'])
            if stored['status'] == 'PENDING':
                stored['note'] = 'An earlier attempt may still be running or its outcome is unknown. No automatic resend.'
            return stored
        raise ValueError('The shared demo limit of three email attempts per UTC day has been reached.') from exc
    try:
        result = client('sesv2').send_email(FromEmailAddress=cfg.ses_verified_sender,
            Destination={'ToAddresses':[cfg.demo_email_recipient]},Content={'Raw':{'Data':payload}})
        receipt.update(status='ACCEPTED_BY_SES',message_id=result['MessageId'],
            request_id=result['ResponseMetadata']['RequestId'],http_status=result['ResponseMetadata']['HTTPStatusCode'])
        telemetry.emit({'category':'SES_V2','service':'sesv2','operation':'send_email','execution_mode':'LIVE_AWS',
            'episode_id':state.episode_id,'message_id':receipt['message_id'],'request_id':receipt['request_id'],
            'http_status':receipt['http_status'],'request':{'destination':'verified-demo-inbox',
                'packet_sha256':state.audit['sha256']},'response':{'MessageId':receipt['message_id']}})
    except Exception as exc:
        # Never infer rejection from a network timeout. An accepted send may have lost its response.
        receipt.update(status='OUTCOME_UNKNOWN',note='Sending failed or its outcome is uncertain. No automatic resend; inspect AWS evidence.')
        if isinstance(exc,ClientError):
            code = exc.response.get('Error',{}).get('Code','Unknown')
            receipt['error_code'] = code
            if 400 <= exc.response.get('ResponseMetadata',{}).get('HTTPStatusCode',0) < 500:
                receipt['status'] = 'REJECTED_BY_SES'
                receipt['note'] = 'AWS rejected this attempt. No automatic retry; inspect the recorded AWS error code.'
        else:
            receipt['error_code'] = type(exc).__name__
        telemetry.emit({'category':'SES_V2','service':'sesv2','operation':'send_email',
            'execution_mode':'AWS_ERROR','episode_id':state.episode_id,
            'error':receipt['error_code'],'request':{'destination':'verified-demo-inbox'}})
        db.update_item(TableName=cfg.memory_table,Key=key,UpdateExpression='SET #s = :s',
            ExpressionAttributeNames={'#s':'State'},ExpressionAttributeValues={':s':{'S':json.dumps(receipt)}})
        return receipt
    # If this write fails the PENDING reservation still blocks duplicates after a restart.
    db.update_item(TableName=cfg.memory_table,Key=key,UpdateExpression='SET #s = :s',
        ExpressionAttributeNames={'#s':'State'},ExpressionAttributeValues={':s':{'S':json.dumps(receipt)}})
    return receipt
