import json

from aws_client import call, not_sent
from config import settings


class AWSCDSEngine:
    def dispatch(self, channel: str, service: str, operation: str, payload: dict,
                 category: str, configured: bool) -> dict:
        if not settings().channel_enabled(channel):
            return not_sent(service, operation, payload, category,
                            f'{channel} not enabled; account onboarding or sender configuration required. No message sent.')
        return call(service, operation, payload, category, configured=configured)

    def send_whatsapp_clinical_message(self, destination_phone: str, text_body: str,
                                       interactive_buttons: list | None = None) -> dict:
        content = {'messaging_product': 'whatsapp', 'to': destination_phone.lstrip('+'),
                   'type': 'text', 'text': {'body': text_body}}
        if interactive_buttons:
            content = {'messaging_product': 'whatsapp', 'to': destination_phone.lstrip('+'),
                'type': 'interactive', 'interactive': {'type': 'button', 'body': {'text': text_body},
                'action': {'buttons': [{'type': 'reply', 'reply': {'id': b['id'], 'title': b['title'][:20]}}
                                      for b in interactive_buttons[:3]]}}}
        return self.dispatch('WHATSAPP', 'socialmessaging', 'send_whatsapp_message', {
            'originationPhoneNumberId': settings().whatsapp_origination_id,
            'message': json.dumps(content).encode(), 'metaApiVersion': settings().whatsapp_meta_api_version},
            'SOCIALMESSAGING', configured=bool(settings().whatsapp_origination_id))

    def send_rcs_pharmacy_carousel(self, destination_phone: str, patient_name: str, rx_options: list) -> dict:
        cards = [{'Title': option['title'], 'Description': f"{option['copay']} copay | {option['eta']} | {patient_name}",
                  'Suggestions': [{'Reply': {'Text': option['action'], 'PostbackData': option['id']}}]}
                 for option in rx_options]
        return self.dispatch('RCS', 'pinpoint-sms-voice-v2', 'send_rcs_message', {
            'DestinationPhoneNumber': destination_phone, 'OriginationIdentity': settings().rcs_origination_id,
            'RcsMessageContent': {'Content': {'Carousel': {'CardWidth': 'MEDIUM', 'CardContents': cards}}}},
            'PINPOINT_RCS', configured=bool(settings().rcs_origination_id))

    def send_sms_deadzone_failover(self, destination_phone: str, caregiver_phone: str,
                                   episode_id: str, alert_text: str) -> list[dict]:
        text = f'PulseContinuum {episode_id}: {alert_text} Data link lost. Reply 1: request nurse + meds; 2: on-call clinician.'
        return [self.dispatch('SMS', 'pinpoint-sms-voice-v2', 'send_text_message', {
            'DestinationPhoneNumber': phone, 'OriginationIdentity': settings().sms_origination_id,
            'MessageBody': text, 'MessageType': 'TRANSACTIONAL'}, 'PINPOINT_SMS',
            configured=bool(settings().sms_origination_id)) for phone in dict.fromkeys([destination_phone, caregiver_phone])]

    def send_ses_clinical_escalation_email(self, physician_email: str, subject: str, html_report: str,
                                         raw_message: bytes | None = None) -> dict:
        content = {'Raw': {'Data': raw_message}} if raw_message else {'Simple': {
            'Subject': {'Data': subject}, 'Body': {'Html': {'Data': html_report}}}}
        allowed = [email.strip().lower() for email in settings().allowed_email_recipients.split(',') if email.strip()]
        if settings().aws_mode == 'live' and physician_email.lower() not in allowed:
            return not_sent('sesv2', 'send_email', {'To': physician_email}, 'SES_V2',
                            'Recipient is not in the approved test-recipient allowlist. No email sent.')
        return self.dispatch('SES', 'sesv2', 'send_email', {'FromEmailAddress': settings().ses_verified_sender,
            'Destination': {'ToAddresses': [physician_email]}, 'Content': content}, 'SES_V2',
            configured=bool(settings().ses_verified_sender))


def build_mcp():
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('PulseContinuum CDS dispatcher')
    engine = AWSCDSEngine()
    server.tool()(engine.send_whatsapp_clinical_message)
    server.tool()(engine.send_rcs_pharmacy_carousel)
    server.tool()(engine.send_sms_deadzone_failover)
    server.tool()(engine.send_ses_clinical_escalation_email)
    return server


if __name__ == '__main__':
    build_mcp().run(transport='stdio')
