All commands below run from the repository root unless a `cd` is shown.

# Development and integration guide

Post-discharge continuity across WhatsApp, RCS, SMS, and Amazon SES. Five focused screens show the care cohort, an interactive patient/caregiver workbench, identity graph and execution trace, pharmacy requests and audit vault, and raw AWS telemetry.

## Run locally

Python 3.11+ and Node.js 20+ are required. The supplied Dockerfile uses Python 3.11. This workspace was built using Python 3.13 and Node 22; see `VERIFICATION.md` for actual checks.

```bash
chmod +x start_demo.sh
./start_demo.sh
```

On Windows:

```powershell
.\start_demo.ps1
```

Open http://localhost:3000 and http://localhost:8000/docs. Both launchers install dependencies, build Next.js, start both servers, and clean up on exit. For separate terminals:

```bash
python -m venv .venv
# Activate .venv using your platform's activation script
python -m pip install -r backend/requirements.txt
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
# Second terminal:
cd frontend
npm ci
npm run build
npm start
```

## Three-minute demonstration

1. Select Rajesh Sharma, `EP-2026-409`, on the live workbench. Ingest the sample discharge PDF. Two physician medication rows appear and a WhatsApp check-in is generated.
2. Submit the seeded symptom transcript, optionally with a real JPEG/PNG/WebP label photo and an audio note. Reported fever/dizziness routes to clinical review. In demo mode, photos are **unverified**, not falsely identified. The curated demo interaction rule flags possible duplicate NSAID use from the reported blue tablet. Switch the patient phone to RCS to inspect three actionable cards.
3. Flip the data blackout switch, or wait 15 seconds without a delivery receipt. Patient and caregiver SMS messages appear. Reply `1` for a nurse/medication request or `2` for clinical triage.
4. Inspect the reserved request and SES HTML/PDF audit on Pharmacy & audit. Repeated replies return the existing order. Inspect requests, responses, execution mode, latency, MessageId, and RequestId on AWS telemetry. Reset is available only in demo mode; use another synthetic episode in live mode.

Six fictional episodes can run this flow independently: surgical recovery, cardiac stent recovery, knee replacement, asthma follow-up, wound care, and heart-failure follow-up. Each has a synthetic history, discharge observations, allergies, care-team handoff, follow-up slot, and its own labeled discharge PDF. The workbench's Clinical context panel shows these details and loads the selected patient's report. The dataset lives in `backend/sample_assets/synthetic_cohort.json`; regenerate its PDF fixtures with `python tools/generate_synthetic_assets.py`.

Demo JSON state persists in `backend/.data`; the connected AWS workspace uses `backend/.data-live` plus DynamoDB. All patient records, pharmacy inventory, copays, courier ETAs, and tele-triage slots are fixtures. Telephone identities use the fictional +1-202-555-01xx range. No real patient identities or hospital records were imported. No measured readmission reduction, clinical accuracy, or cost savings are claimed.

## API

| Endpoint | Input / purpose |
| --- | --- |
| `GET /api/health` | Configuration health, storage/runtime mode |
| `GET /api/patients` | Seeded episodes |
| `GET /api/patients/{episode_id}` | Full synchronized episode |
| `POST /api/workflow/ingest-discharge` | Multipart `episode_id`, optional PDF `file` |
| `POST /api/workflow/whatsapp-multimodal` | Multipart `episode_id`, `transcript`, optional `image`, `audio` |
| `POST /api/workflow/simulate-deadzone-failover` | JSON `episode_id` |
| `POST /api/workflow/caregiver-sms-reply` | JSON `episode_id`, `reply` (`1` / `2`) |
| `POST /api/workflow/rcs-action` | JSON `episode_id`, `option_id` (`generic`, `brand`, `triage`) |
| `POST /api/workflow/reset` | Demo-only episode reset |
| `GET /api/pharmacy` | Demo inventory / copay options |
| `GET /api/telemetry` | Optional `category`, `after` filters |
| `WS /ws/events` | Bounded event stream with heartbeat and reconnect support |
| `GET /api/audits/{episode_id}.pdf` | Generated clinical audit PDF |
| `POST /api/webhooks/delivery` | Authenticated normalized delivery receipt |
| `POST /api/webhooks/inbound` | Authenticated normalized message/action |
| `POST /api/webhooks/ses` | Multipart episode + inbound MIME file with PDF attachment |

The discharge parser deliberately accepts explicit `MEDICATION|name|strength|schedule` and `RED_FLAG|text` rows. Scanned PDFs and other layouts return a review error instead of inventing prescriptions. Audio uploads are retained and playable; triage uses the supplied English/Hindi/Telugu transcript. Automatic speech recognition is not implemented.

## AWS configuration

Copy `.env.example` to `backend/.env`. Demo is the default and performs no AWS calls. In live mode boto3 uses the normal AWS credential provider chain, never embedded keys. Populate AWS origination identities, verified SES sender, table and bucket names, optional Bedrock Guardrail ID, and an existing AgentCore Runtime ARN. Set `ALLOW_DEMO_FALLBACK=false` when failures must stop the workflow. Otherwise each failed AWS call is visibly labeled `DEMO_FALLBACK` with its error. Missing service configuration is also visible. Demo records never fabricate HTTP statuses or AWS RequestIds.

RCS uses the real `send_rcs_message` carousel API with a **separate RCS agent identity**. It does not send SMS and label it RCS. WhatsApp uses `send_whatsapp_message`; SMS sends separately to the patient and caregiver; SES sends a MIME email containing HTML and an attached PDF. Bedrock uses `converse` with actual image bytes. The deterministic formulary gate always runs after model output, even with managed Guardrails enabled.

`agentcore/memory_graph.py` is a custom DynamoDB episode/identity store, not the managed AgentCore Memory service. The DAG runs locally in the FastAPI process; an existing managed AgentCore Runtime can additionally be invoked using its ARN. MCP dispatcher and pharmacy servers are real FastMCP stdio servers:

```bash
cd backend
python -m mcp_gateway.cds_dispatcher_mcp
python -m mcp_gateway.pharmacy_erp_mcp
```

The application calls the same registered tool implementations locally. Managed AgentCore Gateway provisioning and an external pharmacy ERP are deployment integrations; no managed Gateway or real fulfillment is claimed by the demo.

## CDK

```bash
python -m pip install -r infra/requirements.txt
cd infra
cdk synth
# Review the template, configure account/region, then deploy when ready.
```

The stack provisions an encrypted, retained DynamoDB table with identity GSI and point-in-time recovery; a private encrypted/versioned clinical asset bucket; SES MIME receipt rules; an SNS delivery topic; encrypted inbound/DLQ queues; AWS delivery rules; and a 15-second SQS-delayed Lambda watchdog. SES rule-set activation, verified domains, MX routing, WhatsApp/RCS onboarding, messaging registrations, model access, and service quotas are account prerequisites. The receipt rule set is not activated automatically. Output values map to `.env.example`.

EventBridge cannot itself wait 15 seconds; the deployed timer uses SQS message delay. The local demo has an asyncio watchdog. Set `INBOUND_QUEUE_URL` to start the IAM-authenticated SNS/SQS consumer. It handles WhatsApp text and delivery envelopes, SMS replies, RCS action IDs, timeout events, and SES S3 receipt notifications. SES MIME must contain `X-Pulse-Episode-ID`; unknown formats retry to the DLQ. Configure WABA and SMS/RCS two-way destinations to the output SNS topic and grant the supplied publisher role. Native WhatsApp media events require a trusted media-download adapter to the multipart endpoint; direct uploads already work. Webhooks require `X-Webhook-Token`; this is **not** a public endpoint that blindly trusts an SNS envelope. Never expose it as an unauthenticated SNS subscription.

## Clinical and deployment boundaries

This is a hackathon decision-support application, not a certified clinical system. No tablet identity is inferred from color. The formulary gate demands exact drug/strength matching and a readable label. Model output is advisory; pharmacy requests remain pending clinician approval. No real prescription, nurse dispatch, inventory reservation, or appointment booking occurs in the demo ERP.

Clinical audit packets include a SHA-256 digest and HMAC-SHA256 over the canonical payload (available in episode JSON). These provide payload integrity with a shared secret, not an asymmetric physician signature, DKIM replacement, or digitally signed PDF. Supply a secret signing key before live use.

The server binds to loopback by default. Live mode requires `API_TOKEN` and all clinical REST requests require `Authorization: Bearer ...`. The local Next.js server proxy injects a private `BACKEND_API_TOKEN` from `.env.local`; the browser never receives it. Live telemetry uses an authenticated upstream SSE connection at `/api/events`, while the direct WebSocket contract remains available for authenticated clients. Never put the token in a public `NEXT_PUBLIC_*` variable. This local proxy is not a replacement for user authentication on a public deployment. Restrict raw telemetry because it intentionally includes payloads. Production requires user authentication/authorization, clinical consent, retention/deletion controls, tenant isolation, encryption-key policies, approved integrations, audit review, and a suitable AWS BAA where applicable. No cloud resources are deployed by the launch scripts.

## Verified connected prototype

The application has been exercised locally against S3, DynamoDB, Bedrock Nova Pro, EventBridge and SES with synthetic inputs. See [sanitized AWS evidence](../submission/aws-verification-summary.json). Local connection manifests, credentials and raw runtime state are excluded from this repository.

## Verify

```bash
python -m pytest -q
python -m ruff check backend infra
python -m compileall -q backend infra
cd frontend
npm run typecheck
npm run lint
npm run build
```

Tests cover the complete care loop, exact-strength/readability guardrails, upload and webhook rejection, live adapter payloads with botocore Stubber, timeout behavior, stale receipts, durable local state, WebSockets, and duplicate fulfillment suppression. Stubbed SDK tests are not proof of delivery to AWS or a handset.

## References

- [AWS RCS carousel API](https://docs.aws.amazon.com/boto3/latest/reference/services/pinpoint-sms-voice-v2/client/send_rcs_message.html)
- [AgentCore runtime invocation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)

MIT licensed. See `LICENSE` and `MARKETPLACE_DEPLOYMENT.md`.

## Submission materials

See [submission guide](../submission/README.md), [architecture](../submission/ARCHITECTURE.md), and [three-minute recording script](../submission/DEMO_SCRIPT.md). Run `python tools/evaluate_submission.py` for offline safety checks and `python tools/package_submission.py` for a source archive that excludes credentials and runtime records. Public hosting must set `REQUIRE_JUDGE_AUTH=true`, `JUDGE_USERNAME`, and a strong `JUDGE_PASSWORD`, and expose only HTTPS for the frontend. The backend stays private.
