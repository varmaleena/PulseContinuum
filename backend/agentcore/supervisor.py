import asyncio
import hashlib
import hmac
import html
import io
import json
import textwrap
from email.message import EmailMessage

from agentcore.coordination import apply_event, open_coordination, tick
from agentcore.memory_graph import MemoryGraph
from agentcore.vision_forensics import analyze_patient_submission
from artifact_store import save_artifact
from aws_client import call, client, not_sent
from botocore.exceptions import ClientError
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
    for line in [part for value in lines for part in (textwrap.wrap(str(value), width=90) or [''])]:
        y -= 23
        if y < 60:
            pdf.showPage()
            pdf.setFont('Helvetica', 10)
            y = 780
        pdf.drawString(50, y, line)
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
            if state.order or state.analysis:
                raise ValueError('Reset this synthetic episode before replacing a discharge plan with analyzed evidence or an active handoff.')
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
            if state.order:
                raise ValueError('Reset this synthetic episode before analyzing a new report; the current handoff must remain consistent.')
            if not state.ingested:
                raise ValueError('Ingest the physician discharge plan first.')
            state.demo_replay = None
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
            state.rcs_cards = [option for option in analysis['recommended_rcs_cards'] if option['id'] == 'triage']
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
            self.message(state, 'RCS', 'A clinician review request is available. The app has not changed the medication plan.', result, destination=state.phone)
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
            report = next((message.text for message in reversed(state.messages)
                if message.channel == 'WHATSAPP' and message.direction == 'inbound' and message.media_type != 'audio'),
                'Reported post-discharge symptoms need clinician review.')
            results = self.cds.send_sms_deadzone_failover(state.phone, state.caregiver_phone,
                episode_id, report[:120])
            for phone, result in zip(dict.fromkeys([state.phone, state.caregiver_phone]), results):
                self.message(state, 'SMS', result['request']['MessageBody'], result, destination=phone)
            self.trace(state, 'Omnichannel Router & Failover Agent', 'Prepared patient/caregiver fallback; inspect each message delivery status', detail)
            state.stage = 'Caregiver response pending'
            if all(result['execution_mode'] == 'NOT_SENT' for result in results):
                state.active_channel = 'LOCAL_REVIEW'
                state.stage = 'Fallback preview only; SMS sender not connected'
            return self.commit(state)

    async def fulfill(self, episode_id: str, option_id: str = 'generic', reply: str = '1', channel: str = 'SMS') -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            if option_id != 'triage' and channel != 'SMS':
                raise ValueError('Medication delivery is not authorized by an AI label check. Request clinician review instead.')
            if state.order:
                return state
            if not state.analysis or (channel == 'SMS' and not state.blackout):
                raise ValueError('No active care request to confirm.')
            # A caregiver response requests review, never medication dispensing.
            option_id = 'triage'
            state.caregiver_confirmed_at = now() if channel == 'SMS' else None
            state.delivery_status = 'ACKNOWLEDGED'
            self.message(state, channel, reply if channel == 'SMS' else f'Request {option_id}', direction='inbound')
            state.order = reserve_order(episode_id, option_id)
            open_coordination(state)
            state.stage = 'Clinical review requested; clinician decision pending'
            self.trace(state, 'Care Handoff Coordinator', 'Idempotent synthetic review request; no dispensing or consultation performed', state.order)
            pdf = self.refresh_handoff(state)
            subject, report = state.audit['subject'], state.audit['html']
            mime = EmailMessage()
            mime['Subject'] = subject
            mime['From'] = settings().ses_verified_sender or 'demo@example.org'
            mime['To'] = state.physician_email
            mime.set_content('Clinical review required. See attached signed-payload audit.')
            mime.add_alternative(report, subtype='html')
            mime.add_attachment(pdf, maintype='application', subtype='pdf', filename='clinical-audit.pdf')
            result = (not_sent('sesv2','send_email',{},'SES_V2','Use the explicit bounded demo-email action; no automatic email.')
                if settings().explicit_email_only else
                self.cds.send_ses_clinical_escalation_email(state.physician_email, subject, report, mime.as_bytes()))
            state.audit.update({'message_id': result['message_id'], 'mode': result['execution_mode']})
            self.message(state, 'SES', subject, result, destination=state.physician_email)
            return self.commit(state)


    def refresh_handoff(self, state: PatientState) -> bytes:
        report_text = next((message.text for message in reversed(state.messages)
            if message.direction == 'inbound' and message.channel == 'WHATSAPP' and message.media_type != 'audio'), 'No patient report recorded')
        canonical = json.dumps({'episode_id':state.episode_id,'order':state.order,'analysis':state.analysis,
            'confirmation':state.caregiver_confirmed_at,'patient_report':report_text,
            'clinical_review':state.clinical_review,'patient_acknowledgement':state.patient_acknowledgement,
            'follow_up_record':state.follow_up_record,'evidence_source':state.demo_replay,
            'coordination':state.coordination},sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        signature = hmac.new(settings().audit_signing_key.encode(),canonical.encode(),hashlib.sha256).hexdigest()
        subject = f'Care review handoff | {state.episode_id} | {state.name}'
        sections = [('Written discharge plan','; '.join(f'{m.name} {m.strength}: {m.schedule}' for m in state.medications)),
            ('Patient report',report_text), ('Reported red flags','; '.join(state.red_flags) or 'No model-reported flags; this does not establish clinical safety'),('Why review is needed',(state.analysis or {}).get('summary','Pending evidence')),
            ('Clinical request',state.order['status'] if state.order else 'Not requested'),
            ('Synthetic clinician decision',state.clinical_review['care_plan'] if state.clinical_review else 'Pending clinician review; no medication authorization'),
            ('Recorded review notes',state.clinical_review['notes'] if state.clinical_review else 'Not recorded'),
            ('Patient/caregiver teach-back',state.patient_acknowledgement['teach_back'] if state.patient_acknowledgement else 'Not recorded'),
            ('Follow-up',state.follow_up_record['note'] if state.follow_up_record else (state.profile.follow_up if state.profile else 'Not recorded')),
            ('Coordination ownership', '; '.join(f'{item["id"]}: {item["owner"]} ({item["status"]})' for item in (state.coordination or {}).get('tasks',{}).values()) or 'Not started'),
            ('Outcome','Recovery and real-world assessment are not verified by this synthetic demonstration.')]
        report = '<h1>Care review handoff</h1><p>SYNTHETIC DEMONSTRATION — no prescription or clinical approval is issued by this app.</p>'
        report += f'<p>{html.escape(state.name)} · {html.escape(state.episode_id)}</p>'
        report += ''.join(f'<h3>{html.escape(title)}</h3><p>{html.escape(str(value))}</p>' for title,value in sections)
        report += f'<p>Payload SHA-256: {digest}</p>'
        pdf = make_pdf('PulseContinuum Care Handoff',['SYNTHETIC DEMONSTRATION',state.name,state.episode_id,
            'Clinician review required. No new prescription issued.',*[f'{title}: {value}' for title,value in sections],
            f'SHA-256: {digest}',f'HMAC: {signature}'])
        artifact_key = f'{state.episode_id}-audit-{digest[:20]}.pdf'
        save_artifact(artifact_key,pdf,'application/pdf')
        state.audit = {'subject':subject,'html':report,'sha256':digest,'hmac_sha256':signature,
            'canonical_payload':canonical,'message_id':None,'mode':'NOT_SENT','timestamp':now(),
            'pdf_url':f'/api/audits/{state.episode_id}.pdf','artifact_key':artifact_key,
            'purpose':'Doctor handoff and workflow record; not a prescription or proof of recovery.'}
        return pdf

    def require_demo_handoff(self, state: PatientState):
        if not state.is_synthetic or not state.order:
            raise ValueError('Create a review request for a synthetic episode first.')

    async def clinical_review(self, episode_id: str, decision: str, notes: str) -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            self.require_demo_handoff(state)
            if state.clinical_review:
                return state
            analysis = state.analysis or {}
            if (state.risk_score >= 70 or state.red_flags) and decision != 'CLINICIAN_CONTACT':
                raise ValueError('Reported symptom flags require an assessment request in this demonstration.')
            if decision == 'FOLLOW_DISCHARGE_PLAN' and (state.risk_score >= 70 or state.red_flags
                or not analysis.get('guardrail_verification',{}).get('dosage_verified')
                or analysis.get('interactions',{}).get('duplicate_nsaid_risk')):
                raise ValueError('Unresolved symptoms or medication evidence require assessment/reconciliation, not routine-plan clearance.')
            plans = {
                'CLINICIAN_CONTACT':'Request assessment by the treating clinical team. Assessment has not been confirmed. The app makes no medication changes.',
                'MEDICATION_RECONCILIATION':'Request readable medication labels and reconciliation with the treating clinician. The app authorizes no substitution or dose change.',
                'FOLLOW_DISCHARGE_PLAN':'Record review of the existing written discharge plan. No medication changes are made by the app; follow-up remains required.'}
            state.clinical_review = {'decision':decision,'notes':notes,'care_plan':plans[decision],
                'recorded_at':now(),'recorded_by':'Demonstration clinician role','simulation':True,'medication_changes_made':False}
            state.order['status'] = 'REVIEW_RECORDED'
            state.stage = 'Synthetic clinician review recorded; patient acknowledgment pending'
            self.trace(state,'Clinical Review','Recorded synthetic clinician decision; not a verified clinical consultation',{'decision':decision})
            if state.coordination:
                tick(state)
            self.refresh_handoff(state)
            return self.commit(state)

    async def acknowledge_plan(self, episode_id: str, actor: str, teach_back: str) -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            self.require_demo_handoff(state)
            if not state.clinical_review:
                raise ValueError('Record a clinician review before patient acknowledgment.')
            if state.patient_acknowledgement:
                return state
            state.patient_acknowledgement = {'actor':actor,'teach_back':teach_back,'recorded_at':now(),
                'simulation':True,'understanding_automatically_verified':False}
            state.stage = 'Patient/caregiver plan acknowledgment recorded; follow-up pending'
            self.trace(state,'Care Coordination','Recorded synthetic teach-back; understanding still requires human assessment')
            if state.coordination:
                tick(state)
            self.refresh_handoff(state)
            return self.commit(state)

    async def record_follow_up(self, episode_id: str, outcome: str, note: str) -> PatientState:
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            self.require_demo_handoff(state)
            if not state.patient_acknowledgement:
                raise ValueError('Record patient/caregiver acknowledgment before follow-up.')
            if state.follow_up_record:
                return state
            state.follow_up_record = {'outcome':outcome,'note':note,'recorded_at':now(),'simulation':True,
                'planned_follow_up':state.profile.follow_up if state.profile else '', 'recovery_verified':False}
            state.order['status'] = 'REASSESSMENT_REQUIRED' if outcome == 'REASSESSMENT_REQUESTED' else 'FOLLOW_UP_RECORDED'
            state.stage = 'Follow-up recorded; reassessment requested' if outcome == 'REASSESSMENT_REQUESTED' else 'Follow-up contact recorded; recovery outcome not verified'
            self.trace(state,'Follow-up Coordination',state.stage,{'outcome':outcome})
            if state.coordination:
                tick(state)
            self.refresh_handoff(state)
            return self.commit(state)

    async def replay_scenario(self, episode_id: str) -> PatientState:
        from pathlib import Path
        catalog = json.loads((Path(__file__).parent.parent/'sample_assets/high_risk_scenarios.json').read_text(encoding='utf-8'))
        if episode_id not in {scenario['episode_id'] for scenario in catalog} or not settings().serverless:
            raise ValueError('Choose a published hosted synthetic scenario.')
        async with self.lock(episode_id):
            try:
                response = client('s3').get_object(Bucket=settings().assets_bucket,Key=f'scenarios/{episode_id}.json')
                evidence = json.loads(response['Body'].read(1024*1024))
                response['Body'].close()
            except ClientError as exc:
                raise ValueError('The recorded AWS scenario is not available yet.') from exc
            state = PatientState.model_validate(evidence['state'])
            if state.episode_id != episode_id or not state.is_synthetic or not state.analysis or not evidence.get('model_request_id'):
                raise ValueError('The scenario evidence could not be validated.')
            state.order = state.audit = state.clinical_review = state.patient_acknowledgement = state.follow_up_record = None
            state.coordination = None
            state.blackout = False
            state.caregiver_confirmed_at = state.pending_message_id = None
            state.delivery_status = 'NOT_SENT'
            state.analysis['execution_mode'] = 'RECORDED_AWS_RUN'
            state.demo_replay = {'original_model_request_id':evidence['model_request_id'],
                'recorded_at':evidence['recorded_at'],'loaded_at':now(),
                'description':'Replay of recorded AWS inference; no new Bedrock request on this action.'}
            state.stage = 'Recorded AWS analysis loaded; clinician review request pending'
            metadata = response['ResponseMetadata']
            telemetry.emit({'category':'SCENARIO_REPLAY','service':'s3','operation':'get_object',
                'execution_mode':'LIVE_AWS','request_id':metadata['RequestId'],'http_status':metadata['HTTPStatusCode'],
                'analysis_mode':'RECORDED_AWS_RUN','episode_id':episode_id})
            self.trace(state,'Scenario Evidence','Loaded recorded AWS analysis, not a fresh model inference',state.demo_replay)
            return self.commit(state)

    async def coordinate(self, command) -> PatientState:
        async with self.lock(command.episode_id):
            state = self.memory.get(command.episode_id)
            self.require_demo_handoff(state)
            if not state.coordination:
                raise ValueError('Replay and open a new handoff to use coordination events.')
            apply_event(state, command)
            self.trace(state, 'Handoff Policy Controller', 'Processed correlated synthetic coordination event',
                state.coordination['last_event_result'])
            self.refresh_handoff(state)
            return self.commit(state)

    async def send_demo_email(self, episode_id: str) -> PatientState:
        from agentcore.demo_email import send_packet
        async with self.lock(episode_id):
            state = self.memory.get(episode_id)
            self.require_demo_handoff(state)
            if episode_id not in self.memory.templates:
                raise ValueError('Only the published synthetic fixture episodes may be emailed.')
            state.email_receipt = send_packet(state)
            self.trace(state,'SES Handoff','Explicit synthetic email attempt; no clinical treatment or inbox delivery inferred',
                {'status':state.email_receipt['status']})
            return self.commit(state)

    async def coordination_tick(self):
        changed = []
        for episode_id in list(self.memory.states):
            async with self.lock(episode_id):
                state = self.memory.get(episode_id)
                if not state.is_synthetic or not state.coordination or not state.order:
                    continue
                if not any(item['status'] == 'OPEN' for item in state.coordination['tasks'].values()):
                    continue
                if tick(state):
                    state.coordination['scheduler_last_checked_at'] = now()
                    self.trace(state, 'Handoff Policy Controller', 'AWS scheduled deadline check; no model call or outbound send')
                    self.refresh_handoff(state)
                    self.commit(state)
                    changed.append(episode_id)
        return {'checked':len(self.memory.states), 'updated':changed, 'outbound_sent':False}
