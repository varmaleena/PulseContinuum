from typing import Any, Literal

from pydantic import BaseModel, Field


class Medication(BaseModel):
    name: str
    strength: str
    schedule: str


class CDSMessage(BaseModel):
    id: str
    channel: Literal['WHATSAPP', 'RCS', 'SMS', 'SES']
    direction: str = 'outbound'
    text: str
    timestamp: str
    status: str = 'SIMULATED'
    media_url: str | None = None
    media_type: str | None = None
    destination: str = ''


class AgentTrace(BaseModel):
    agent: str
    action: str
    status: str = 'PASS'
    timestamp: str
    details: dict[str, Any] = Field(default_factory=dict)


class ClinicalProfile(BaseModel):
    dataset_id: str
    reference_date: str
    sex: str
    admitted_at: str
    discharged_at: str
    facility: str
    care_unit: str
    clinician: str
    caregiver_relation: str
    preferred_language: str
    history: list[str]
    allergies: list[str]
    discharge_vitals: dict[str, str]
    handoff_note: str
    follow_up: str
    scenario: str
    patient_report: str


class PatientState(BaseModel):
    episode_id: str
    patient_id: str
    name: str
    age: int
    condition: str
    day: int
    phone: str
    caregiver_phone: str
    physician_email: str
    is_synthetic: bool = True
    profile: ClinicalProfile | None = None
    active_channel: str = 'WHATSAPP'
    risk_score: int = 18
    stage: str = 'Monitoring'
    medications: list[Medication] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    messages: list[CDSMessage] = Field(default_factory=list)
    traces: list[AgentTrace] = Field(default_factory=list)
    analysis: dict[str, Any] | None = None
    rcs_cards: list[dict[str, Any]] = Field(default_factory=list)
    order: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    blackout: bool = False
    ingested: bool = False
    pending_message_id: str | None = None
    delivery_status: str = 'NONE'
    caregiver_confirmed_at: str | None = None
    clinical_review: dict[str, Any] | None = None
    patient_acknowledgement: dict[str, Any] | None = None
    follow_up_record: dict[str, Any] | None = None
    demo_replay: dict[str, Any] | None = None
    coordination: dict[str, Any] | None = None


class ClinicalReviewRequest(BaseModel):
    episode_id: str
    decision: Literal['CLINICIAN_CONTACT', 'MEDICATION_RECONCILIATION', 'FOLLOW_DISCHARGE_PLAN']
    notes: str = Field(min_length=10, max_length=1500)


class AcknowledgementRequest(BaseModel):
    episode_id: str
    actor: Literal['PATIENT', 'CAREGIVER']
    teach_back: str = Field(min_length=10, max_length=1500)


class FollowUpRequest(BaseModel):
    episode_id: str
    outcome: Literal['CONTACT_RECORDED', 'REASSESSMENT_REQUESTED']
    note: str = Field(min_length=10, max_length=1500)


class WorkflowRequest(BaseModel):
    episode_id: str = 'EP-2026-409'
    reply: Literal['1', '2'] = '1'
    option_id: Literal['generic', 'brand', 'triage'] = 'generic'
    event_id: str | None = None


class DeliveryEvent(BaseModel):
    episode_id: str | None = None
    address: str | None = None
    message_id: str
    status: Literal['DELIVERED', 'READ', 'FAILED', 'UNDELIVERED', 'TIMEOUT']
    event_id: str


class CoordinationCommand(BaseModel):
    episode_id: str
    run_id: str = Field(min_length=8, max_length=80)
    event_id: str = Field(min_length=8, max_length=100)
    kind: Literal['ADVANCE_CLOCK', 'DELIVERY_FAILED', 'DELIVERED', 'CAREGIVER_REPLY', 'CONCERN_REPORTED']
    task_id: str = Field(default='', max_length=100)
    correlation_id: str = Field(default='', max_length=100)
    text: str = Field(default='', max_length=1000)
    advance_seconds: int = Field(default=0, ge=0, le=900)
