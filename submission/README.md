# PulseContinuum AI submission

PulseContinuum preserves a single synthetic recovery episode across discharge intake, patient evidence, caregiver fallback, and a clinician audit. The differentiator is continuity with inspectable execution evidence and explicit safety gates.

## What works

- Five-page frontend with separate Care team and Admin & engineering profiles, authenticated FastAPI backend, six distinct fictional recovery cases, and downloadable discharge PDFs.
- Real S3 storage, DynamoDB persistence, Nova Pro multimodal analysis, EventBridge events, and one approved SES audit submission verified in the connected account.
- Deterministic readable-label/name/strength gate, structured model-output validation, stale receipt protection, idempotent request fulfillment, and signed audit payloads.
- Offline regression results: `evaluation-results.json`. These measure code behavior, not clinical outcomes or model accuracy.

## Honest boundaries

WhatsApp/SMS/RCS delivery remains unavailable because account service subscription is blocked. Their local adapters demonstrate the intended flow and explicitly show NOT_SENT in live mode. Pharmacy inventory, prices, appointments and order reservations are synthetic. No medication is prescribed or purchased. Risk scores are unvalidated review signals. The orchestrator is local Python with MCP tool definitions; managed AgentCore Runtime/Memory/Gateway are not deployed. Managed Bedrock Guardrails are optional and currently unconfigured. Audio uses the entered transcript, without automatic speech recognition. Inbound SES domain routing is not activated.

## Judge walkthrough

Start with `DEMO_SCRIPT.md`; use `ARCHITECTURE.md` for the system boundary. Local launch instructions are in the root README. All records and files provided in the repository are synthetic. Use demo mode for a repeatable complete simulated workflow without cloud costs. Live mode must not silently fall back to demo responses.

## Remaining submission actions

- Publish the sanitized source to https://github.com/varmaleena/PulseContinuum and verify its contents.
- Deploy and verify an HTTPS application URL with private judge credentials, within the agreed AWS budget. Keep access available throughout judging.
- Record and upload a public approximately three-minute video using the script. Supply its URL.
- Complete the event submission form with repository, application, video and architecture links.

These actions are intentionally listed as pending until their URLs and actual verification exist. A source archive alone is not a submitted entry.
