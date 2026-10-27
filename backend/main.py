import asyncio
import contextlib
import hashlib
import hmac
import io
from contextlib import asynccontextmanager
from email import policy
from email.parser import BytesParser
from pathlib import Path

from agentcore.supervisor import Supervisor
from artifact_store import load_artifact, save_artifact
from aws_client import client
from config import settings
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from mcp_gateway.pharmacy_erp_mcp import inventory
from models.schemas import (
    AcknowledgementRequest,
    ClinicalReviewRequest,
    CoordinationCommand,
    DeliveryEvent,
    FollowUpRequest,
    WorkflowRequest,
)
from telemetry import telemetry

supervisor = Supervisor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    telemetry.loop = asyncio.get_running_loop()
    supervisor.memory.hydrate()
    worker = None
    if settings().aws_mode == 'live' and settings().inbound_queue_url:
        from agentcore.inbound_worker import consume
        worker = asyncio.create_task(consume(supervisor))
    yield
    if worker:
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
    for task in supervisor.timeouts.values():
        task.cancel()
    await asyncio.gather(*supervisor.timeouts.values(), return_exceptions=True)
    telemetry.loop = None


app = FastAPI(title='PulseContinuum AI', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins.split(','),
                   allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['*'])


def authorize(authorization: str | None = Header(default=None)):
    if settings().aws_mode == 'live' and not settings().api_token:
        raise HTTPException(503, 'API_TOKEN is required in live mode')
    if settings().api_token and not hmac.compare_digest(authorization or '', f'Bearer {settings().api_token}'):
        raise HTTPException(401, 'Invalid API token')


api_auth = [Depends(authorize)]


@app.post('/api/workflow/coordination-event', dependencies=api_auth)
async def coordination_event(body: CoordinationCommand):
    return await supervisor.coordinate(body)


@app.exception_handler(KeyError)
async def missing(request: Request, exc: KeyError):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail': 'Unknown patient episode or identity'}, status_code=404)


@app.exception_handler(ValueError)
async def invalid(request: Request, exc: ValueError):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail': str(exc)}, status_code=422)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': settings().aws_mode, 'region': settings().aws_region,
            'synthetic_reset': settings().allow_synthetic_reset,
            'account_id': settings().aws_account_id,
            'channels': {name: settings().channel_enabled(name) for name in ['WHATSAPP', 'RCS', 'SMS', 'SES']},
            'memory': 'DynamoDB' if settings().memory_table and settings().aws_mode == 'live' else 'Local demo JSON',
            'runtime': 'Configured AWS AgentCore' if settings().agentcore_runtime_arn else 'Local orchestrator',
            'erp': 'Demo inventory', 'audio': 'Uploaded audio + supplied transcript'}


@app.get('/api/events', dependencies=api_auth)
async def event_stream(request: Request):
    if settings().serverless:
        raise HTTPException(409, 'Hosted mode uses bounded telemetry polling')
    import json

    from fastapi.responses import StreamingResponse

    async def generate():
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        telemetry.subscribers.add(queue)
        try:
            for event in list(telemetry.events):
                yield f'data: {json.dumps(event)}\n\n'
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                except TimeoutError:
                    event = {'category': 'HEARTBEAT'}
                yield f'data: {json.dumps(event)}\n\n'
        finally:
            telemetry.subscribers.discard(queue)
    return StreamingResponse(generate(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.exception_handler(RuntimeError)
async def service_error(request: Request, exc: RuntimeError):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail': str(exc)}, status_code=502)


@app.get('/api/patients', dependencies=api_auth)
def patients():
    if settings().serverless:
        return [supervisor.memory.get(episode_id) for episode_id in supervisor.memory.states]
    return list(supervisor.memory.states.values())


@app.get('/api/patients/{episode_id}', dependencies=api_auth)
def patient(episode_id: str):
    return supervisor.memory.get(episode_id)


@app.get('/api/telemetry', dependencies=api_auth)
def logs(category: str | None = None, after: int = 0):
    if settings().serverless:
        import json
        result = client('dynamodb').query(TableName=settings().memory_table,
            KeyConditionExpression='EpisodeID = :episode', ExpressionAttributeValues={':episode':{'S':'TELEMETRY#HOSTED'}},
            ScanIndexForward=False, Limit=100)
        records = [json.loads(item['State']['S']) for item in result.get('Items',[])]
        return [record for record in reversed(records) if record['id'] > after and (not category or record.get('category') == category)]
    return [e for e in telemetry.events if e['id'] > after and (not category or e.get('category') == category)]


@app.get('/api/pharmacy', dependencies=api_auth)
def pharmacy():
    return inventory()


@app.get('/api/scenarios', dependencies=api_auth)
def scenarios():
    import json

    from botocore.exceptions import ClientError
    rows = json.loads((Path(__file__).parent/'sample_assets/high_risk_scenarios.json').read_text(encoding='utf-8'))
    for row in rows:
        row['available'] = False
        if settings().serverless:
            try:
                client('s3').head_object(Bucket=settings().assets_bucket,Key=f'scenarios/{row["episode_id"]}.json')
                row['available'] = True
            except ClientError:
                pass
    return rows


@app.post('/api/workflow/replay-scenario', dependencies=api_auth)
async def replay_scenario(body: WorkflowRequest):
    return await supervisor.replay_scenario(body.episode_id)


@app.get('/api/fixtures/{episode_id}/discharge.pdf', dependencies=api_auth)
def synthetic_discharge(episode_id: str):
    supervisor.memory.get(episode_id)
    path = Path(__file__).parent / 'sample_assets' / f'{episode_id}-discharge.pdf'
    if not path.is_file():
        raise HTTPException(404, 'Synthetic fixture not found')
    return FileResponse(path, media_type='application/pdf')


async def read_upload(file: UploadFile, maximum: int = 8 * 1024 * 1024) -> bytes:
    data = await file.read(maximum + 1)
    if len(data) > maximum:
        raise HTTPException(413, 'Upload exceeds 8 MB limit')
    return data


@app.post('/api/workflow/ingest-discharge', dependencies=api_auth)
async def ingest(episode_id: str = Form('EP-2026-409'), file: UploadFile | None = File(None)):
    fixture = Path(__file__).parent / 'sample_assets' / f'{episode_id}-discharge.pdf'
    if not fixture.exists():
        fixture = Path(__file__).parent / 'sample_assets/sample_discharge_summary.pdf'
    data = await read_upload(file) if file else fixture.read_bytes()
    if not data.startswith(b'%PDF'):
        raise HTTPException(422, 'A PDF discharge summary is required')
    from pypdf.errors import PdfReadError
    try:
        return await supervisor.ingest(episode_id, data)
    except PdfReadError as exc:
        raise HTTPException(422, 'The PDF could not be parsed') from exc


@app.post('/api/workflow/whatsapp-multimodal', dependencies=api_auth)
async def multimodal(episode_id: str = Form('EP-2026-409'),
                     transcript: str = Form('I took the blue tablet. I have a 101.2F fever and dizziness.'),
                     image: UploadFile | None = File(None), audio: UploadFile | None = File(None)):
    if len(transcript) > 12000:
        raise HTTPException(422, 'Transcript too long')
    image_data = await read_upload(image) if image else None
    image_format = 'jpeg'
    image_url = None
    audio_url = None
    media_dir = Path(settings().data_dir) / 'media'
    media_dir.mkdir(exist_ok=True)
    if image_data:
        from PIL import Image
        try:
            decoded = Image.open(io.BytesIO(image_data))
            decoded.verify()
            image_format = {'JPEG': 'jpeg', 'PNG': 'png', 'WEBP': 'webp'}.get(decoded.format or '', '')
            if not image_format:
                raise ValueError('Unsupported image')
        except Exception:
            raise HTTPException(422, 'Provide a valid JPEG, PNG, or WebP image')
        name = hashlib.sha256(image_data).hexdigest() + '.' + image_format
        save_artifact(f'media/{name}', image_data, f'image/{image_format}')
        image_url = f'/api/media/{name}'
    if audio:
        if audio.content_type not in ('audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/webm', 'audio/ogg', 'audio/mp4'):
            raise HTTPException(422, 'Unsupported audio type')
        data = await read_upload(audio)
        suffix = {'audio/mpeg': 'mp3', 'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a'}[audio.content_type]
        name = hashlib.sha256(data).hexdigest() + '.' + suffix
        save_artifact(f'media/{name}', data, audio.content_type or 'application/octet-stream')
        audio_url = f'/api/media/{name}'
    return await supervisor.multimodal(episode_id, transcript, image_data, image_format, image_url, audio_url)


@app.post('/api/workflow/simulate-deadzone-failover', dependencies=api_auth)
async def deadzone(body: WorkflowRequest):
    return await supervisor.failover(body.episode_id)


@app.post('/api/workflow/caregiver-sms-reply', dependencies=api_auth)
async def sms_reply(body: WorkflowRequest):
    return await supervisor.fulfill(body.episode_id, body.option_id, body.reply)


@app.post('/api/workflow/rcs-action', dependencies=api_auth)
async def rcs_action(body: WorkflowRequest):
    return await supervisor.fulfill(body.episode_id, body.option_id, '1', 'RCS')


@app.post('/api/workflow/clinical-review', dependencies=api_auth)
async def clinical_review(body: ClinicalReviewRequest):
    return await supervisor.clinical_review(body.episode_id, body.decision, body.notes)


@app.post('/api/workflow/acknowledge-plan', dependencies=api_auth)
async def acknowledge_plan(body: AcknowledgementRequest):
    return await supervisor.acknowledge_plan(body.episode_id, body.actor, body.teach_back)


@app.post('/api/workflow/follow-up', dependencies=api_auth)
async def follow_up(body: FollowUpRequest):
    return await supervisor.record_follow_up(body.episode_id, body.outcome, body.note)


@app.post('/api/workflow/reset', dependencies=api_auth)
async def reset(body: WorkflowRequest):
    if settings().aws_mode != 'demo' and not settings().allow_synthetic_reset:
        raise HTTPException(403, 'Reset is demo-only')
    from agentcore.memory_graph import seed
    async with supervisor.lock(body.episode_id):
        if not supervisor.memory.get(body.episode_id).is_synthetic:
            raise HTTPException(403, 'Only synthetic episodes can be reset')
        if body.episode_id in supervisor.timeouts:
            supervisor.timeouts[body.episode_id].cancel()
        return supervisor.commit(seed()[body.episode_id])


def webhook_auth(token: str | None):
    if not settings().webhook_token or not hmac.compare_digest(token or '', settings().webhook_token):
        raise HTTPException(401, 'Webhook token required')


@app.post('/api/webhooks/delivery')
async def delivery(body: DeliveryEvent, x_webhook_token: str | None = Header(None)):
    webhook_auth(x_webhook_token)
    episode_id = body.episode_id or supervisor.memory.resolve(body.address or '')
    if body.status in ('FAILED', 'UNDELIVERED', 'TIMEOUT'):
        return await supervisor.failover(episode_id, body.status, body.message_id)
    async with supervisor.lock(episode_id):
        state = supervisor.memory.get(episode_id)
        if state.pending_message_id == body.message_id:
            state.delivery_status = body.status
            for message in state.messages:
                if message.id == body.message_id:
                    message.status = body.status
            supervisor.commit(state)
        return state


@app.post('/api/webhooks/inbound')
async def inbound(body: dict, x_webhook_token: str | None = Header(None)):
    """Normalized ingress contract for a trusted SNS/WhatsApp adapter, not an unsigned public SNS endpoint."""
    webhook_auth(x_webhook_token)
    episode_id = supervisor.memory.resolve(body.get('address', ''))
    if body.get('channel') == 'SMS':
        if body.get('text') not in ('1', '2'):
            raise HTTPException(422, 'Reply 1 or 2')
        return await supervisor.fulfill(episode_id, reply=body['text'])
    if body.get('channel') == 'RCS':
        if body.get('option_id') not in ('generic', 'brand', 'triage'):
            raise HTTPException(422, 'Unknown action')
        return await supervisor.fulfill(episode_id, body['option_id'], channel='RCS')
    return await supervisor.multimodal(episode_id, str(body.get('text', '')))


@app.post('/api/webhooks/ses')
async def ses_inbound(episode_id: str = Form(...), file: UploadFile = File(...), x_webhook_token: str | None = Header(None)):
    webhook_auth(x_webhook_token)
    mime = BytesParser(policy=policy.default).parsebytes(await read_upload(file))
    for attachment in mime.iter_attachments():
        if attachment.get_content_type() == 'application/pdf':
            return await supervisor.ingest(episode_id, attachment.get_payload(decode=True))
    raise HTTPException(422, 'No PDF attachment found')


@app.get('/api/media/{name}', dependencies=api_auth)
def media(name: str):
    if not all(c.isalnum() or c == '.' for c in name) or '..' in name:
        raise HTTPException(404)
    path = load_artifact(f'media/{name}')
    if path is None:
        raise HTTPException(404)
    return FileResponse(path)


@app.get('/api/audits/{episode_id}.pdf', dependencies=api_auth)
def audit_pdf(episode_id: str):
    state = supervisor.memory.get(episode_id)
    if not state.audit:
        raise HTTPException(404, 'Generate an audit by confirming a care request')
    path = load_artifact(f'{episode_id}-audit.pdf')
    if path is None:
        raise HTTPException(404, 'Generate an audit by confirming a care request')
    return FileResponse(path, media_type='application/pdf', filename=f'{episode_id}-audit.pdf')


@app.websocket('/ws/events')
async def websocket(ws: WebSocket):
    if settings().api_token and not hmac.compare_digest(ws.headers.get('authorization', ''), f'Bearer {settings().api_token}'):
        await ws.close(code=1008)
        return
    if settings().aws_mode == 'live' and not settings().api_token:
        await ws.close(code=1008)
        return
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    telemetry.subscribers.add(queue)
    async def send():
        for event in list(telemetry.events):
            await ws.send_json(event)
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), 20)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({'category': 'HEARTBEAT'})
    sender = asyncio.create_task(send())
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender
        telemetry.subscribers.discard(queue)
