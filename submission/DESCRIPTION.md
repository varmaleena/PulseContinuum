# PulseContinuum AI

## Problem

After discharge, a patient's report, caregiver response and medication context can become disconnected as communication shifts between channels. A missing delivery receipt should not also mean losing the recovery story.

## Solution

PulseContinuum associates each interaction with a single recovery episode. It ingests an explicit discharge plan, evaluates submitted text and medication-label evidence with Amazon Bedrock, applies a deterministic formulary check, and demonstrates caregiver escalation and a signed clinician audit. Five pages expose cohort context, the workflow, orchestration, pending pharmacy requests and AWS telemetry.

## AWS implementation

The connected prototype uses Amazon S3 for discharge assets, DynamoDB for episode persistence, Bedrock Nova Pro for multimodal inference, EventBridge with SNS/SQS/Lambda infrastructure for continuity events, and Amazon SES for an approved synthetic audit email. Runtime telemetry records actual request IDs and execution mode. SES API acceptance has been verified; inbox delivery has not been established.

Phone-channel adapters for AWS End User Messaging are implemented, but live WhatsApp, RCS and SMS remain blocked by account subscription/onboarding. The application labels these attempts NOT_SENT. The current orchestrator runs in Python; managed AgentCore services are not deployed.

## Demonstration and validation

Six fictional recovery pathways contain distinct synthetic histories, discharge PDFs, medication plans, caregiver context and symptom reports. Offline safety cases exercise unreadable labels, mismatched strengths, unknown medications, mixed evidence and invalid model risk scores. Backend regression tests cover the clinical loop, authorization, invalid uploads, idempotency, stale receipts and native event handling. These are engineering checks, not evidence of clinical benefit.

## Value and next steps

The prototype demonstrates an inspectable handoff between patient evidence and clinician review. Its proposed value is reduced context loss across care channels; clinical outcomes and financial savings require prospective validation. Next steps are phone-channel onboarding, durable hosted audit/media storage, a real provider integration and supervised evaluation. Pharmacy prices and reservations remain fixtures, all requests await clinician approval, and the prototype must use synthetic data only.
