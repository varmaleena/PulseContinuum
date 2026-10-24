import base64
import json
import time
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from config import settings
from telemetry import telemetry


def serial(value: Any) -> Any:
    if isinstance(value, bytes):
        return {'base64': base64.b64encode(value).decode(), 'length': len(value)}
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serial(v) for v in value]
    return value


@lru_cache
def client(service: str):
    session = boto3.Session(profile_name=settings().aws_profile or None)
    return session.client(service, region_name=settings().aws_region,
                        config=Config(connect_timeout=4, read_timeout=30, retries={'max_attempts': 1}))


def call(service: str, operation: str, payload: dict, category: str,
         demo: dict | None = None, configured: bool = True) -> dict:
    start = time.perf_counter()
    mode = 'DEMO'
    error = None
    aws_error_response = None
    response: dict = demo or {'MessageId': f'demo-{telemetry.sequence + 1:06d}'}
    if settings().aws_mode == 'live' and configured:
        try:
            response = getattr(client(service), operation)(**payload)
            # Streaming bodies must be consumed while the request is in scope.
            if 'response' in response and hasattr(response['response'], 'read'):
                response['response'] = response['response'].read().decode()
            if 'Body' in response and hasattr(response['Body'], 'read'):
                response['Body'] = response['Body'].read(8 * 1024 * 1024 + 1)
            mode = 'LIVE_AWS'
            if response.get('FailedEntryCount', 0):
                raise RuntimeError(json.dumps(response.get('Entries')))
        except Exception as exc:
            error = str(exc)
            aws_error_response = serial(getattr(exc, 'response', None))
            mode = 'DEMO_FALLBACK' if settings().allow_demo_fallback else 'AWS_ERROR'
            response = (demo or {'MessageId': f'demo-fallback-{telemetry.sequence + 1:06d}'}) if settings().allow_demo_fallback else {}
    elif settings().aws_mode == 'live':
        error = 'Service configuration missing'
        mode = 'DEMO_FALLBACK' if settings().allow_demo_fallback else 'AWS_ERROR'
    metadata = (aws_error_response or response).get('ResponseMetadata', {})
    result = {'service': service, 'operation': operation, 'category': category,
              'execution_mode': mode, 'request': serial(payload), 'response': serial(response),
              'message_id': response.get('MessageId', response.get('messageId')),
              'request_id': metadata.get('RequestId'),
              'http_status': metadata.get('HTTPStatusCode'),
              'latency_ms': round((time.perf_counter() - start) * 1000, 2), 'error': error,
              'aws_error_response': aws_error_response}
    telemetry.emit(result)
    if mode == 'AWS_ERROR':
        raise RuntimeError(error)
    return result


def not_sent(service: str, operation: str, payload: dict, category: str, reason: str) -> dict:
    """A disabled real-world channel must never generate a fake success or MessageId."""
    result = {'service': service, 'operation': operation, 'category': category,
              'execution_mode': 'NOT_SENT', 'request': serial(payload), 'response': {},
              'message_id': None, 'request_id': None, 'http_status': None, 'latency_ms': 0,
              'error': reason}
    telemetry.emit(result)
    return result
