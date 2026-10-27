"""Buffered Lambda ASGI adapter: bounded requests, no resident worker or SSE."""
import asyncio
import hmac
import json
import time
import uuid

from aws_client import client
from botocore.exceptions import ClientError
from config import settings
from main import app, supervisor
from mangum import Mangum
from telemetry import telemetry

adapter = Mangum(app, lifespan='off')
initialized = False


def handler(event, context):
    global initialized
    scheduled = (not event.get('requestContext') and event.get('source') == 'pulsecontinuum.coordination'
                 and event.get('detail-type') == 'CoordinationTick')
    supplied = {key.lower():value for key,value in event.get('headers',{}).items()}.get('authorization','')
    if not scheduled and (not settings().api_token or not hmac.compare_digest(supplied, 'Bearer '+settings().api_token)):
        return {'statusCode':401, 'headers':{'content-type':'application/json','cache-control':'no-store'},
                'body':'{"detail":"Backend service authentication required"}'}
    telemetry.events.clear()
    if not initialized:
        supervisor.memory.hydrate()
        initialized = True
    owner = None
    lease_key = {'EpisodeID':{'S':'LOCK#WORKFLOW'}, 'EntityKey':{'S':'GLOBAL'}}
    if scheduled or event.get('rawPath','').startswith('/api/workflow/'):
        owner = uuid.uuid4().hex
        try:
            client('dynamodb').put_item(TableName=settings().memory_table,
                Item={**lease_key, 'LeaseUntil':{'N':str(int(time.time())+75)}, 'LeaseOwner':{'S':owner}},
                ConditionExpression='attribute_not_exists(LeaseUntil) OR LeaseUntil < :now',
                ExpressionAttributeValues={':now':{'N':str(int(time.time()))}})
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
            if scheduled:
                raise RuntimeError('Coordination lease busy; EventBridge must retry the tick') from exc
            return {'statusCode':409, 'headers':{'content-type':'application/json'},
                    'body':'{"detail":"Another care action is running. Please retry shortly."}'}
    try:
        if scheduled:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(supervisor.coordination_tick())
            print(json.dumps({'coordination_tick':result}))
            return result
        return adapter(event, context)
    finally:
        if owner:
            try:
                client('dynamodb').delete_item(TableName=settings().memory_table,Key=lease_key,
                    ConditionExpression='LeaseOwner = :owner',ExpressionAttributeValues={':owner':{'S':owner}})
            except ClientError:
                print('Workflow lease release failed; lease will expire automatically')
        # Persist metadata and bounded payloads across cold starts. No credentials are stored.
        # Polling reads are not persisted again: idle dashboards must not create a write loop.
        records = list(telemetry.events) if scheduled or event.get('rawPath','').startswith('/api/workflow/') else []
        for record in records:
            entry = dict(record)
            entry['id'] = int(time.time() * 1_000_000)
            def bounded(value):
                if isinstance(value, dict):
                    if 'base64' in value:
                        return {'length':value.get('length'), 'omitted':'binary artifact'}
                    return {key: bounded(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [bounded(item) for item in value]
                if isinstance(value, str) and len(value) > 12000:
                    return value[:12000] + ' [truncated]'
                return value
            entry = bounded(entry)
            encoded = json.dumps(entry, default=str)
            if len(encoded.encode()) > 30000:
                entry = {key:value for key,value in entry.items() if key not in ('request','response')}
                entry['payload_note'] = 'Payload omitted to keep the durable event bounded.'
            try:
                client('dynamodb').put_item(TableName=settings().memory_table, Item={
                    'EpisodeID':{'S':'TELEMETRY#HOSTED'},
                    'EntityKey':{'S':f'EVENT#{entry["timestamp"]}#{uuid.uuid4().hex}'},
                    'State':{'S':json.dumps(entry,default=str)},
                    'ExpiresAt':{'N':str(int(time.time())+7*86400)}})
            except Exception:
                # CloudWatch still records the failure; do not change a committed workflow response.
                print('Hosted telemetry persistence failed')
