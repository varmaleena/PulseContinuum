"""IAM-authenticated SNS -> SQS ingress; unknown payloads retry into the configured DLQ."""
import asyncio
import base64
import json
from email import policy
from email.parser import BytesParser

from aws_client import call
from config import settings
from telemetry import telemetry


def object_bytes(bucket: str, key: str) -> bytes:
    if bucket != settings().assets_bucket:
        raise ValueError('Inbound assets must be in the configured clinical bucket')
    result = call('s3', 'get_object', {'Bucket': bucket, 'Key': key}, 'SES_INBOUND', demo={})
    body = result['response'].get('Body', {})
    data = base64.b64decode(body['base64'])
    if len(data) > 8 * 1024 * 1024:
        raise ValueError('Inbound object exceeds 8 MB')
    return data


async def process_event(supervisor, event: dict):
    if 'Message' in event:
        event = json.loads(event['Message'])
    if 'detail' in event:
        event = event['detail']
    if event.get('status') in ('FAILED', 'UNDELIVERED', 'TIMEOUT') and event.get('episode_id'):
        return await supervisor.failover(event['episode_id'], event['status'], event.get('message_id'))
    if 'whatsAppWebhookEntry' in event:
        entry = event['whatsAppWebhookEntry']
        entry = json.loads(entry) if isinstance(entry, str) else entry
        for change in entry.get('changes', []):
            value = change.get('value', {})
            for receipt in value.get('statuses', []):
                episode = supervisor.memory.resolve('+' + receipt['recipient_id'].lstrip('+'))
                status = receipt['status'].upper()
                if status == 'FAILED':
                    await supervisor.failover(episode, status, receipt['id'])
                elif status in ('DELIVERED', 'READ'):
                    async with supervisor.lock(episode):
                        state = supervisor.memory.get(episode)
                        if state.pending_message_id == receipt['id']:
                            state.delivery_status = status
                            supervisor.commit(state)
            for message in value.get('messages', []):
                episode = supervisor.memory.resolve('+' + message['from'].lstrip('+'))
                if message['type'] != 'text':
                    # Media retrieval is performed by a trusted adapter; do not follow arbitrary URLs.
                    raise ValueError('Media event requires normalized trusted upload via multipart endpoint')
                await supervisor.multimodal(episode, message['text']['body'])
        return
    if 'originationNumber' in event:
        episode = supervisor.memory.resolve(event['originationNumber'])
        body = event.get('messageBody', '').strip()
        action = event.get('postbackData', body)
        if action in ('generic', 'brand', 'triage'):
            return await supervisor.fulfill(episode, action, channel='RCS')
        if body in ('1', '2'):
            return await supervisor.fulfill(episode, reply=body)
        raise ValueError('Unsupported inbound response')
    if event.get('notificationType') == 'Received' and event.get('receipt', {}).get('action', {}).get('type') == 'S3':
        action = event['receipt']['action']
        data = object_bytes(action['bucketName'], action['objectKey'])
        mime = BytesParser(policy=policy.default).parsebytes(data)
        # The episode id must be explicitly supplied by the hospital. No name-based identity guesses.
        episode = mime.get('X-Pulse-Episode-ID')
        if not episode:
            raise ValueError('Hospital MIME requires X-Pulse-Episode-ID')
        for part in mime.iter_attachments():
            if part.get_content_type() == 'application/pdf':
                return await supervisor.ingest(episode, part.get_payload(decode=True))
        raise ValueError('No discharge PDF attachment')
    raise ValueError('Unsupported inbound envelope')


async def consume(supervisor):
    while True:
        try:
            result = await asyncio.to_thread(call, 'sqs', 'receive_message', {
                'QueueUrl': settings().inbound_queue_url, 'WaitTimeSeconds': 10, 'MaxNumberOfMessages': 1},
                'AWS_INGRESS', {})
            if result['execution_mode'] != 'LIVE_AWS':
                await asyncio.sleep(5)
                continue
            for message in result['response'].get('Messages', []):
                try:
                    await process_event(supervisor, json.loads(message['Body']))
                    call('sqs', 'delete_message', {'QueueUrl': settings().inbound_queue_url,
                        'ReceiptHandle': message['ReceiptHandle']}, 'AWS_INGRESS')
                except Exception as exc:
                    telemetry.emit({'category': 'AWS_INGRESS', 'operation': 'process_event', 'error': str(exc),
                                    'message_id': message['MessageId'], 'execution_mode': 'RETRY_TO_DLQ'})
        except Exception as exc:
            telemetry.emit({'category': 'AWS_INGRESS', 'error': str(exc), 'execution_mode': 'AWS_ERROR'})
            await asyncio.sleep(5)
