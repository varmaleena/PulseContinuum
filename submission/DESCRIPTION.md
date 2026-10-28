## Inspiration

A delivered message is not a completed handoff.

After discharge, a patient may report a new symptom, share an unclear medication photo, or lose connectivity. A caregiver may respond through another channel. The next person reviewing the case needs the full context: what was prescribed, what the patient reported, what remains uncertain, and who is responsible for the next step.

PulseContinuum AI explores how that recovery context can stay connected as evidence, people and communication paths change.

## What it does

PulseContinuum connects discharge instructions, patient evidence, caregiver responses and review tasks to one recovery episode.

The workflow moves from **discharge plan → patient check-in → evidence review → clinician handoff → teach-back → follow-up**. Medication-label matching is kept separate from permission to change treatment. Unresolved evidence remains a review task.

Once a handoff opens, a bounded policy controller assigns owners and operational deadlines. An unconfirmed patient contact can create a caregiver contact intent. An unanswered review escalates to an on-call role. Repeated failures reach manual intervention instead of disappearing into a success state. Correlated replies stay attached to the existing case; duplicate events cannot create duplicate tasks.

Care teams see the patient workflow. A separate Admin & engineering view exposes the execution timeline and AWS evidence behind it.

## How we built it

The frontend uses **Next.js, React and TypeScript**, hosted on Vercel. A server-side proxy connects it to a **FastAPI backend on AWS Lambda** without exposing backend credentials to the browser.

**Amazon Bedrock Nova Pro** interprets submitted text and medication-label images. Pydantic schemas validate model output, while deterministic checks compare medication evidence with the written discharge formulary.

**DynamoDB** persists episode state, task ownership and event fingerprints. **Amazon S3** stores synthetic discharge files, media, recorded scenario evidence and versioned handoff PDFs. **EventBridge** invokes the deadline worker every five minutes, independently of an open browser. Bounded retries and an **SQS failure destination** preserve failed worker events for inspection.

The **Amazon SES** integration uses Boto3 and includes a fixed verified demo inbox, a shared daily attempt limit and explicit acceptance or uncertain-outcome records. Generating a packet does not automatically email it. Infrastructure is defined with **AWS CDK**.

## Challenges we ran into

The hardest problems appeared after the first successful analysis: delayed receipts, repeated replies, failed contacts and unanswered review requests. We introduced run-specific correlation IDs, persisted event fingerprints and a DynamoDB workflow lease to keep these transitions consistent.

Another failure case involved updating a PDF before the corresponding state save succeeded. Content-versioned artifacts now preserve the previously committed packet when a later save fails.

Communication onboarding also shaped the prototype. Phone-channel delivery remains a preview. The email path distinguishes API acceptance, rejection and uncertainty rather than reporting every attempt as delivered.

## Accomplishments that we're proud of

- A deployed five-page application with distinct care and engineering views.
- Three high-risk synthetic scenarios covering postoperative symptoms, wound deterioration with conflicting medication evidence, and heart-failure symptoms with caregiver fallback.
- **46 passing backend tests** and **49 public coordination assertions** across the three scenarios.
- Actual AWS scheduled-worker executions verified through CloudWatch evidence.
- Persistent ownership, bounded escalation, duplicate suppression and an inspectable handoff packet.

These are engineering results, not measurements of clinical accuracy, reduced readmissions or financial savings.

## What we learned

Reliable coordination requires more than a model response. The system must distinguish evidence from authorization, delivery from acknowledgment, and a recorded contact from a resolved concern.

We also learned to make uncertainty visible. Recorded AWS inference is labeled as recorded, synthetic communication events remain synthetic, and a missing provider response does not become a successful send. The model assists evidence interpretation; explicit policies and human review determine what happens next.

## What's next for PulseContinuum AI

The next steps are verified two-way communication, supervised feedback from care coordinators, and evaluation against realistic operational workflows. Further work includes hospital identity and tenant isolation, consent management, EHR integration and a scalable due-task queue.

The current application uses synthetic records only. Its owners are demonstration roles, its accelerated deadlines are operational examples, and it does not prescribe, dispense medicine or establish clinical recovery.
