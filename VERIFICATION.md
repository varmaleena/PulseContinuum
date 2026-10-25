# Build and demo verification

Verified locally on 24 October 2026 using Windows, Python 3.13.14 and Node.js 22.14.0.

| Check | Result |
| --- | --- |
| Next.js production build | PASS: all five application routes generated |
| TypeScript validation | PASS: no errors |
| ESLint | PASS: no warnings or errors |
| Python compileall | PASS |
| Ruff backend/infra checks | PASS |
| Backend pytest suite | PASS: 12 tests; one third-party Starlette/httpx deprecation warning |
| Dependency consistency (`pip check`) | PASS |
| CDK synthesis | PASS: template generated; identity GSI, delayed queue, and Lambda event mapping checked |
| MCP registration | PASS: 4 CDS tools and 3 pharmacy tools |
| HTTP smoke checks | PASS: overview, workbench, agentcore, pharmacy-rcs, telemetry and frontend API proxy return 200 |
| Browser demo | PASS: intake, triage, RCS options, SMS fallback, acknowledgment, care reservation and audit |
| Light clinical UI revision | PASS: production build and browser workflow rechecked |
| Phone scroll behavior | PASS: updates scroll within the phone without moving the page |
| Windows launcher parsing | PASS |

The local backend is on port 8000 and frontend on port 3000, in **live AWS mode**, with demo fallback disabled. The UI uses a light clinical theme and a guided three-step workbench. All six episodes are fictional; their histories, discharge observations, allergies, caregiver relations, follow-up slots and PDF records are labeled synthetic. Twelve tests cover the workflow, case-specific discharge parsing, dataset integrity and outbound safeguards.

`PulseContinuumConnected` is deployed in the confirmed AWS account, us-east-1. Actual AWS calls verified S3 PDF upload, DynamoDB write/readback, Bedrock Nova Pro image analysis with validated structured output, and EventBridge publication. SES accepted one synthetic clinical-audit email to the explicitly approved, verified test recipient; a real SES MessageId and RequestId were returned. Inbox delivery was not independently confirmed. Evidence is saved in `live-aws-verification.json`.

Phone-channel account APIs returned `SubscriptionRequiredException`; handset delivery is not enabled or claimed. Managed AgentCore deployment, clinical effectiveness, and external pharmacy fulfillment have not been verified. Both application servers run locally, while their connected services run in AWS. Python 3.11 Docker execution and the Bash launcher were not run on this Windows host. The container targets Python 3.11; actual local verification used Python 3.13.

Known integration boundaries are documented in README.md. Uploaded photos are not embedded in outbound physician audit emails: automatic approval review blocked that addition because of sensitive medical-image egress. Adding that behavior requires explicit approval. Audio uploads use supplied transcripts; direct native WhatsApp media events still require a trusted media-download adapter.

The original stack rolled back because its SES receipt rule lacked SNS publish permission. That permission/dependency was corrected. Automatic approval review blocked cleanup of retained resources, so the successful stack reuses the retained table and bucket. Nothing was deleted. The original rolled-back stack record is preserved.

## Submission hardening — 2026-10-24

- Replaced unverified hospital affiliation with a fictional demo network. Removed illustrative savings/rescue metrics from the overview.
- Added a configurable judge access middleware; public hosting must require it and use HTTPS.
- Offline safety evaluation: 19/19 cases passed (`submission/evaluation-results.json`); this measures deterministic code/schema behavior, not model accuracy or clinical benefit.
- Backend: 12 tests passed; one upstream Starlette/httpx deprecation warning. Ruff and Python compilation passed.
- Added architecture diagram, judge walkthrough, three-minute recording script, submission description, CI workflow and sanitized source packager. CI configuration is supplied; a hosted CI run has not yet occurred.
- Public hosting, published repository and recorded video are still pending. Phone-channel subscription remains blocked.

- Final production Next.js build completed: all five pages, TypeScript, lint and page generation passed.
- Runtime judge access check passed: anonymous page/API and wrong password returned 401; authorized access to all five pages returned 200; required but absent credentials returned 503.
- CDK application synthesis completed without deployment.
- Existing live AWS evidence rechecked read-only; no additional email or model invocation. Sanitized service/request evidence is included in `submission/aws-verification-summary.json`.

## Two-profile separation — 2026-10-24

Care team is the default with three clinical pages; Admin & engineering contains the two technical pages. Production build/TypeScript/lint passed. The executable access verification passed care/API restrictions, forged header/cookie attempts, JSON trace/account redaction, same-origin switching, authorized admin access and missing-configuration fail-closed behavior. Backend regression suite: 12 passed; Ruff clean. The care selector and admin navigation were exercised in the browser and returned to Care team. Local profiles are demonstration views; authenticated hosting uses separate care/admin credentials and requires a private backend.

## Hosted Vercel + Lambda deployment — 2026-10-25

- Vercel production frontend: https://pulsecontinuum.vercel.app; five application pages with a separate sign-in screen.
- AWS Lambda backend deployed in `PulseContinuumWebBackend`; direct unauthenticated requests return 401. Lambda uses an execution role rather than static AWS keys on Vercel.
- A hosted synthetic flow verified S3 discharge upload, validated live Bedrock multimodal output, EventBridge publication, disabled outbound messaging, clinical PDF/media retrieval and durable telemetry. The tested episode was reset afterward. Evidence: `submission/hosted-backend-verification.json`.
- Hosted artifacts persist privately in S3, and workflow telemetry persists in DynamoDB. Idle polling is not persisted as a repeating write stream. Inference attempts are limited atomically to ten per UTC day; a workflow lease guards concurrent mutations.
- Backend regression suite: 14 passed, including cache-loss artifact recovery and inference-allowance rejection. Ruff clean; frontend production build/TypeScript/lint passed.
- Signed browser sign-in/logout, forged-session rejection, care/admin permissions and fail-closed settings passed the executable access verification. Credentials remain private and are excluded from Git/source packages.
- Public frontend API checks verified all three care pages, both admin pages, profile switching, patient data and telemetry. Browser-password-only access was replaced with the sign-in form for clarity.
