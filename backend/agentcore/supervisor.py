import asyncio
import hashlib
import hmac
import html
import io
import json
from email.message import EmailMessage
from pathlib import Path

from agentcore.memory_graph import MemoryGraph
from agentcore.vision_forensics import analyze_patient_submission
from aws_client import call
from config import settings
from mcp_gateway.cds_dispatcher_mcp import AWSCDSEngine
from mcp_gateway.pharmacy_erp_mcp import reserve_order
from models.schemas import AgentTrace, CDSMessage, Medication, PatientState
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from telemetry import now, telemetry


def make_pdf(title: str, lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = 780
    pdf.setTitle(title)
    pdf.setFont('Helvetica-Bold', 18)
    pdf.drawString(50, y, title)
    pdf.setFont('Helvetica', 10)
    for line in lines:
        y -= 23
        if y < 60:
            pdf.showPage()
            pdf.setFont('Helvetica', 10)
            y = 780
        pdf.drawString(50, y, line[:95])
    pdf.save()
    return buffer.getvalue()


class Supervisor:
    def __init__(self):
        self.memory = MemoryGraph()
        self.cds = AWSCDSEngine()
        self.locks: dict[str, asyncio.Lock] = {}
        self.timeouts: dict[str, asyncio.Task] = {}

    def lock(self, episode_id: str) -> asyncio.Lock:
        return self.locks.setdefault(episode_id, asyncio.Lock())

    def trace(self, state: PatientState, agent: str, action: str, details: dict | None = None, status: str = 'PASS'):
        state.traces.append(AgentTrace(agent=agent, action=action, details=details or {}, status=status, timestamp=now()))

    def message(self, state: PatientState, channel: str, text: str, result: dict | None = None,
                direction: str = 'outbound', destination: str = '', media_url: str | None = None,
                media_type: str | None = None):
        result = result or {}
        state.messages.append(CDSMessage(id=result.get('message_id') or f'local-{len(state.messages)+1}',
            channel=channel, text=text, timestamp=now(), direction=direction, destination=destination,
            status=('ACCEPTED' if result.get('execution_mode') == 'LIVE_AWS' else
                    'NOT_SENT' if result.get('execution_mode') == 'NOT_SENT' else
                    'LOCAL_INPUT' if direction == 'inbound' and settings().aws_mode == 'live' else 'SIMULATED'),
            media_url=media_url, media_type=media_type))

    def commit(self, state: PatientState) -> PatientState:
        self.memory.save(state)
        telemetry.emit({'category': 'STATE_UPDATE', 'episode_id': state.episode_id})
        return state

    async def ingest(self, episode_id: str, pdf: bytes) -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(pdf)).pages)
            # A deliberately explicit, auditable discharge format. Unsupported PDFs require review.
            meds = []
            for line in text.splitlines():
                if line.startswith('MEDICATION|'):
                    parts = [part.strip() for part in line.split('|')]
                    if len(parts) == 4:
                        meds.append(Medication(name=parts[1], strength=parts[2], schedule=parts[3]))
            if not meds:
                raise ValueError('No supported physician medication rows found. Use MEDICATION|name|strength|schedule; review scanned PDFs manually.')
            state.medications = meds
            state.red_flags = [line.split('|', 1)[1].strip() for line in text.splitlines() if line.startswith('RED_FLAG|')]
            state.ingested = True
            state.stage = 'Discharge plan synchronized'
            if settings().assets_bucket:
                call('s3', 'put_object', {'Bucket': settings().assets_bucket,
                    'Key': f'{episode_id}/discharge.pdf', 'Body': pdf, 'ContentType': 'application/pdf'}, 'SES_INBOUND')
            self.trace(state, 'Clinical Intake Agent', 'Parsed discharge PDF; physician formulary synchronized', {'medications': len(meds)})
            text_body = f'Hello {state.name.split()[0]}, your discharge plan is ready. Please share a clear medication label photo and describe how you feel. Follow your written prescription.'
            result = self.cds.send_whatsapp_clinical_message(state.phone, text_body)
            self.message(state, 'WHATSAPP', text_body, result, destination=state.phone)
            if result['execution_mode'] == 'NOT_SENT':
                state.active_channel = 'LOCAL_REVIEW'
                state.stage = 'Care plan saved in AWS; WhatsApp not connected'
            return self.commit(state)

    async def multimodal(self, episode_id: str, transcript: str, image: bytes | None = None,
                         image_format: str = 'jpeg', media_url: str | None = None,
                         audio_url: str | None = None) -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            if not state.ingested:
                raise ValueError('Ingest the physician discharge plan first.')
            self.message(state, 'WHATSAPP', transcript, direction='inbound', media_url=media_url, media_type='image' if image else None)
            if audio_url:
                self.message(state, 'WHATSAPP', 'Voice note attached; supplied transcript used for triage.', direction='inbound', media_url=audio_url, media_type='audio')
            if settings().agentcore_runtime_arn:
                call('bedrock-agentcore', 'invoke_agent_runtime', {
                    'agentRuntimeArn': settings().agentcore_runtime_arn,
                    'runtimeSessionId': hashlib.sha256(episode_id.encode()).hexdigest(),
                    'payload': json.dumps({'episode_id': episode_id, 'report': transcript}).encode()},
                    'BEDROCK_AGENTCORE', demo={'response': 'Demo runtime invocation'})
            analysis = analyze_patient_submission(image, transcript, state.model_dump(), image_format)
            state.analysis = analysis
            state.risk_score = analysis['readmission_risk_score']
            state.red_flags = analysis['clinical_red_flags']
            state.rcs_cards = analysis['recommended_rcs_cards']
            state.stage = 'Clinical review required' if state.risk_score >= 70 else 'Medication review'
            self.trace(state, 'Vision & Audio Forensics Agent', 'Evaluated submitted evidence and patient-reported symptoms',
                       {'mode': analysis['execution_mode'], 'interaction_check': analysis['interactions']})
            self.trace(state, 'Bedrock Guardrail Policy Gate', analysis['guardrail_verification']['rule'],
                       analysis['guardrail_verification'], analysis['guardrail_verification']['status'])
            safe_text = ('Your report needs clinical review. Do not take an extra tablet based on its color. '
                         'Contact your treating team promptly about the reported symptoms. If symptoms are severe, seek emergency care.')
            result = self.cds.send_whatsapp_clinical_message(state.phone, safe_text)
            self.message(state, 'WHATSAPP', safe_text, result, destination=state.phone)
            state.pending_message_id = result['message_id']
            state.delivery_status = 'PENDING' if state.pending_message_id else 'NOT_SENT'
            result = self.cds.send_rcs_pharmacy_carousel(state.phone, state.name, state.rcs_cards)
            self.message(state, 'RCS', 'Pharmacy requests and clinical triage options are ready.', result, destination=state.phone)
            state.active_channel = 'RCS' if result['execution_mode'] != 'NOT_SENT' else 'LOCAL_REVIEW'
            self.trace(state, 'Omnichannel Router & Failover Agent',
                       '15-second delivery watchdog armed' if state.pending_message_id else
                       'AWS analysis saved; phone channels unavailable. No delivery watchdog armed.')
            if state.pending_message_id:
                self.arm_timeout(episode_id, state.pending_message_id)
            self.commit(state)
            if settings().aws_mode == 'live' and state.pending_message_id:
                call('events', 'put_events', {'Entries': [{'Source': 'pulsecontinuum.delivery',
                    'DetailType': 'ClinicalAlertPending', 'EventBusName': settings().event_bus_name,
                    'Detail': json.dumps({'episode_id': episode_id, 'message_id': state.pending_message_id})}]},
                    'EVENTBRIDGE_FAILOVER', demo={'FailedEntryCount': 0, 'Entries': [{'EventId': 'demo-pending'}]})
            return state

    def arm_timeout(self, episode_id: str, message_id: str | None):
        if episode_id in self.timeouts:
            self.timeouts[episode_id].cancel()

        async def watchdog():
            await asyncio.sleep(15)
            current = self.memory.get(episode_id)
            if current.pending_message_id == message_id and current.delivery_status == 'PENDING':
                await self.failover(episode_id, 'TIMEOUT', message_id)
        self.timeouts[episode_id] = asyncio.create_task(watchdog())

    async def failover(self, episode_id: str, status: str = 'UNDELIVERED', message_id: str | None = None) -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            if message_id and message_id != state.pending_message_id:
                return state
            if state.blackout or state.caregiver_confirmed_at:
                return state
            if not state.analysis:
                raise ValueError('Submit patient symptoms before triggering failover.')
            state.blackout = True
            state.delivery_status = status
            state.active_channel = 'SMS'
            detail = {'episode_id': episode_id, 'message_id': state.pending_message_id, 'status': status}
            call('events', 'put_events', {'Entries': [{'Source': 'pulsecontinuum.delivery',
                'DetailType': 'ClinicalDeliveryFailure', 'Detail': json.dumps(detail),
                'EventBusName': settings().event_bus_name}]}, 'EVENTBRIDGE_FAILOVER',
                demo={'FailedEntryCount': 0, 'Entries': [{'EventId': 'demo-delivery-failure'}]})
            results = self.cds.send_sms_deadzone_failover(state.phone, state.caregiver_phone,
                episode_id, 'Reported post-discharge symptoms need prompt clinical review.')
            for phone, result in zip(dict.fromkeys([state.phone, state.caregiver_phone]), results):
                self.message(state, 'SMS', result['request']['MessageBody'], result, destination=phone)
            self.trace(state, 'Omnichannel Router & Failover Agent', 'Read unified memory; sent patient and caregiver SMS', detail)
            state.stage = 'Caregiver response pending'
            if all(result['execution_mode'] == 'NOT_SENT' for result in results):
                state.active_channel = 'LOCAL_REVIEW'
                state.stage = 'Fallback preview only; SMS sender not connected'
            return self.commit(state)

    async def fulfill(self, episode_id: str, option_id: str = 'generic', reply: str = '1', channel: str = 'SMS') -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            if state.order:
                return state
            if not state.analysis or (channel == 'SMS' and not state.blackout):
                raise ValueError('No active care request to confirm.')
            if reply == '2':
                option_id = 'triage'
            state.caregiver_confirmed_at = now() if channel == 'SMS' else None
            state.delivery_status = 'ACKNOWLEDGED'
            self.message(state, channel, reply if channel == 'SMS' else f'Request {option_id}', direction='inbound')
            state.order = reserve_order(episode_id, option_id)
            state.stage = 'Request reserved; awaiting clinician approval'
            self.trace(state, 'Pharmacy Fulfillment Agent', 'Idempotent demo reservation; clinician approval required', state.order)
            canonical = json.dumps({'episode_id': episode_id, 'order': state.order, 'analysis': state.analysis,
                                    'confirmation': state.caregiver_confirmed_at}, sort_keys=True)
            digest = hashlib.sha256(canonical.encode()).hexdigest()
            signature = hmac.new(settings().audit_signing_key.encode(), canonical.encode(), hashlib.sha256).hexdigest()
            subject = f'Clinical review requested | {episode_id} | {state.name}'
            report = f'<h1>Clinical escalation & prescription audit</h1><p>{html.escape(state.name)} · {html.escape(episode_id)}</p>'
            report += f'<p>Risk indicator: {state.risk_score}/100 (decision support, not diagnosis).</p>'
            report += '<p>Medication identity remains subject to readable label verification and physician review.</p>'
            report += f'<p>Confirmation: {html.escape(state.caregiver_confirmed_at or "Patient RCS action")}</p>'
            report += '<ul>' + ''.join(f'<li>{html.escape(str(flag))}</li>' for flag in state.red_flags) + '</ul>'
            report += f'<p>Request: {html.escape(state.order["order_id"])}</p><p>SHA-256: {digest}</p><p>HMAC-SHA256: {signature}</p>'
            pdf = make_pdf('PulseContinuum Clinical Audit', [state.name, episode_id,
                f'Risk indicator: {state.risk_score}/100', 'Clinician review required. No new prescription issued.',
                *state.red_flags, f'Order: {state.order["order_id"]}', f'SHA-256: {digest}', f'HMAC: {signature}'])
            audit_path = Path(settings().data_dir) / f'{episode_id}-audit.pdf'
            audit_path.write_bytes(pdf)
            mime = EmailMessage()
            mime['Subject'] = subject
            mime['From'] = settings().ses_verified_sender or 'demo@example.org'
            mime['To'] = state.physician_email
            mime.set_content('Clinical review required. See attached signed-payload audit.')
            mime.add_alternative(report, subtype='html')
            mime.add_attachment(pdf, maintype='application', subtype='pdf', filename='clinical-audit.pdf')
            result = self.cds.send_ses_clinical_escalation_email(state.physician_email, subject, report, mime.as_bytes())
            state.audit = {'subject': subject, 'html': report, 'sha256': digest, 'hmac_sha256': signature,
                'canonical_payload': canonical, 'message_id': result['message_id'], 'mode': result['execution_mode'],
                'timestamp': now(), 'pdf_url': f'/api/audits/{episode_id}.pdf'}
            self.message(state, 'SES', subject, result, destination=state.physician_email)
            return self.commit(state)
