# Architecture and deployed boundaries

![Architecture](architecture.svg)

```mermaid
flowchart LR
  J[Judge / synthetic operator] -->|HTTPS + judge access on public host| N[Next.js: five pages]
  N -->|Private bearer token; SSE proxy| F[FastAPI + local Python orchestrator]
  F --> G[Deterministic label/formulary gate]
  F --> B[Bedrock Nova Pro: real inference]
  F --> D[DynamoDB: episode memory]
  F --> S[S3: synthetic discharge assets]
  F --> E[EventBridge: continuity events]
  F --> M[SES: approved audit email]
  E --> Q[SNS / SQS / timeout Lambda]
  Q --> F
  F -. onboarding blocked .-> P[WhatsApp / RCS / SMS adapters]
  F --> X[Fixture pharmacy + pending clinician request]
  F --> A[Signed audit + local PDF/media]
```

Solid service edges represent implemented adapters; verification evidence is described in the root VERIFICATION.md. The public Next.js frontend runs on Vercel; the hosted FastAPI orchestrator runs on AWS Lambda. The separate local workspace remains available. The frontend never receives the backend token or AWS credentials. SSE uses the server proxy. The optional judge middleware fails closed when `REQUIRE_JUDGE_AUTH=true` but credentials are absent.

The CDK stack provisions shared data/messaging infrastructure. The application orchestrator is not managed AgentCore. MCP servers expose tool definitions, while the current app calls their Python implementations directly. No managed safety policy or validated clinical risk model is claimed.

## Data lifecycle and trust

Only the six labeled synthetic cases are allowed in the hackathon demo. Uploaded PDF text and model output are untrusted. Explicit medication rows are required; invalid evidence fails to clinical review. A label match verifies only name and strength against the written formulary, not dose timing or clinical suitability. Model risk scores are unvalidated.

DynamoDB holds episode state; S3 holds uploaded discharge assets. Hosted audit PDFs and media persist in private S3; Lambda disk is a cache. Local mode retains its local-file behavior. HMAC checks protect audit payload integrity but are not clinician signatures. No EHR, real pharmacy, emergency response or production clinical integration exists.

## Deployment cost boundary

Do not assume App Runner is available: AWS closed it to new customers on April 30, 2026. Candidate hosting must support an IAM execution role, HTTPS, private backend networking, durable artifacts and a cost bounded demo. Static AWS access keys must never be baked into containers. The hosted deployment uses request-based Lambda and DynamoDB billing, with ten model attempts per UTC day and outbound messaging disabled. The $10 authorization is the integration/verification budget, not a guaranteed provider spending cap.

## Profile boundary

Care team is the default experience and receives only allowlisted clinical API responses with raw traces and AWS identifiers removed. Admin & engineering receives the raw event stream and technical pages. A local Demo profiles selector enables presentation; on a secured host, care credentials cannot elevate to admin. See [access design](../docs/ACCESS_PROFILES.md).
