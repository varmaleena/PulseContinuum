from aws_client import call
from config import settings


def verify_medications(identified: list[dict], permitted: list[dict]) -> dict:
    allowed = {(m['name'].casefold(), m['strength'].casefold()) for m in permitted}
    verified = bool(identified) and all(
        (m.get('name', '').casefold(), m.get('strength', '').casefold()) in allowed
        and m.get('label_readable') is True for m in identified)
    return {'status': 'PASS' if verified else 'REVIEW_REQUIRED', 'dosage_verified': verified,
            'rule': 'Exact readable label and strength must match the physician discharge formulary.',
            'guidance': 'Continue only the written discharge plan. Do not infer doses from pill color.'}


def apply_bedrock_guardrail(text: str) -> dict:
    if not settings().bedrock_guardrail_id:
        return {'action': 'NOT_CONFIGURED', 'policy': 'Local deterministic formulary gate active'}
    result = call('bedrock-runtime', 'apply_guardrail', {
        'guardrailIdentifier': settings().bedrock_guardrail_id,
        'guardrailVersion': settings().bedrock_guardrail_version,
        'source': 'OUTPUT', 'content': [{'text': {'text': text}}]}, 'BEDROCK_GUARDRAILS',
        demo={'action': 'DEMO_LOCAL_POLICY'})
    return result['response']
