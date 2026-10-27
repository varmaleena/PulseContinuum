# Independent judge-readiness assessment — 26 October 2026

This is an engineering assessment, not an AWS endorsement or a prediction of judging results.

## Assessment

PulseContinuum has a credible deployed technical foundation. The earlier demonstration was not yet a convincing patient journey: it ended at a pending request, offered pharmacy choices too early and made a generated email look like the end of care. Those were substantive product gaps, not a need for more decorative UI.

The strongest proposition is **an inspectable clinical handoff that retains context when a communication path fails and prevents unsupported medication actions**. A healthcare chatbot, a risk number or an AWS-logo dashboard alone is not distinctive.

The revised workflow explicitly separates AI evidence review, a care-team request, a synthetic clinician decision, patient/caregiver teach-back and a follow-up record. It never treats label matching as medication authorization or a contact record as verified recovery. Those are workflow safeguards, not evidence of clinical efficacy.

## Event requirements and weights

The official event requires an AWS-deployed AI project using at least one qualifying CDS service, source/assets/run instructions, an architecture diagram, a deployed URL, a public roughly three-minute video and a tagged ACE opportunity ID. Its weights are technical execution 40%, demo presentation 20%, value/impact 20%, functionality 10% and creativity 10%. The deadline is 28 October 2026, 13:00 PDT: **29 October, 01:30 IST**. [Official rules](https://aws-cds-partner.devpost.com/rules)

| Area | Evidence / current assessment | Remaining gap |
| --- | --- | --- |
| Technical execution | Vercel frontend, role views, Lambda orchestrator, real Nova Pro inference, DynamoDB, private S3, EventBridge, structured-output checks, workflow lease and idempotent handoffs | The system is a bounded Python workflow; it is not a deployed managed AgentCore multi-agent system |
| Demo clarity | Explicit patient journey, review prerequisites, visible pending states and recorded-case entry points | The three-minute video must show a single understandable story rather than a tour of every service |
| Potential value | A concrete care-transition problem with a plausible operational benefit | No customer study, validated savings, readmission effect or clinical-accuracy measurement exists |
| Functionality | Repeatable engineering checks and recorded real AWS test cases | Phone channels remain previews; no actual pharmacy fulfillment or clinician consultation is verified |
| Creativity | Context-preserving communication fallback plus a safety-constrained handoff | Healthcare AI is an established competition category; the continuity behavior must be the differentiator |

## Comparison with prior recognized projects

| Primary source | What can reasonably be learned | Implication for this project |
| --- | --- | --- |
| [2025 Amazon Nova Partner Demo Competition](https://aws.amazon.com/blogs/apn/celebrating-innovation-announcing-the-2025-amazon-nova-partner-demo-competition-winners/) | The winning TCS outpatient-management demonstration linked agentic workflows to the patient journey; that competition also emphasized Nova Sonic | A healthcare theme is not enough. Show the user journey, the human decision and the resulting action; do not claim Sonic capabilities we do not have |
| [AWS AI Agent Global Hackathon winners](https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon) | EcoLafaek and AegisAgent connect domain evidence to actionable, explainable workflows | Demonstrate what evidence changes the next permitted action, rather than showing agent names alone |
| [2024 PartyRock winners](https://aws.amazon.com/blogs/aws/congratulations-to-the-partyrock-generative-ai-hackathon-winners/) | Recognized entries supplied immediately understandable interactive experiences | Judges should be able to choose a story and understand the result without setup or account friction |

These are different competitions with different criteria. There is no universal “past AWS winner standard” that a project can formally pass.

## CDS fit: the most important competitive limitation

The project has a recorded, genuinely accepted SES SDK submission from the explicitly approved synthetic integration test. Its source contains the real SES, WhatsApp, SMS and RCS adapters. However, **the public hosted demonstration disables all outbound sends**. It must not imply that phone previews reached a handset or that a generated handoff was emailed. This weakens the live omnichannel story even though historical SES execution evidence exists. A dashboard replay is not fresh channel delivery.

Managed AgentCore is not mandatory; the event FAQ accepts custom agents on AWS Lambda. Lack of AgentCore should not be disguised, but it is not by itself a technical disqualification. [Official FAQ](https://aws-cds-partner.devpost.com/details/faq)

## Submission readiness

- Repository, open-source license, architecture and deployed application: available.
- Public judge entry: intentionally no account barrier in public synthetic-demo mode; private backend credentials remain server-side.
- Video: a script exists; a recorded public video URL has not been verified.
- ACE opportunity: an ID with the required campaign tag has not been provided or verified. Corporate-email registration is not a substitute for that deliverable.
- Availability: keep the application usable through judging; preserve recorded-case exploration if the live model allowance is exhausted.
- Claims: no real patients, diagnoses, prescriptions, confirmed clinical recovery, validated business impact, phone delivery or production compliance should be implied.

## Recommendation

Treat this as a promising, submission-capable prototype after the workflow fixes and three-case validation, not as a demonstrated winner. Prioritize a clear three-minute clinical handoff story, candid CDS evidence and completion of the missing submission assets. Do not add more agent labels or unrelated features to compensate for an unclear outcome.

## Coordination-depth update — 27 October 2026

The product now goes beyond manually advancing a handoff: the deployed deterministic controller assigns owners, tracks deadlines, creates caregiver contact intents after failures/timeouts, escalates unanswered review and retains manual-intervention work after bounded retries. Correlated replies, payload-fingerprinted duplicate suppression and late-receipt reconciliation persist with the episode. The public accelerated clock exercises the same reducer as a five-minute EventBridge/Lambda worker.

This strengthens operational and technical depth. It does not remove the live-CDS limitation: the new outbox contains preview intents and is not a real provider dispatch loop. Synthetic role ownership is not authenticated hospital staffing, and these tests establish neither clinical benefit nor a winning probability. See docs/COORDINATION.md for scope and evidence.
