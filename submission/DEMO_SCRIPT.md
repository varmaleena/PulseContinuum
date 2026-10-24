# Three-minute recording script

Prepare: start both servers in **Care team**, use the Demo profiles selector to show **Admin & engineering** for the technical evidence, then return to Care team. On a secured host, use admin/judge credentials for switching. Choose an unused synthetic episode, close account/credential tabs, and verify the AWS telemetry mode. Do not show secrets or a real person's inbox. No extra email is needed: one approved SES acceptance was already verified. Completed episodes are idempotent; use demo mode for reset/replay.

| Time | Screen and action | Narration |
| --- | --- | --- |
| 0:00–0:20 | Clinical overview | “Discharge is a handoff, not the end of care. PulseContinuum keeps recovery context attached to one episode as communication channels change. Every person shown here is fictional.” |
| 0:20–0:50 | Workbench: clinical context and discharge PDF | “Six synthetic pathways have distinct histories and discharge plans. Intake extracts explicit physician medication rows and preserves episode identity in DynamoDB.” |
| 0:50–1:25 | Submit report and synthetic label image | “Nova Pro reviews text and image evidence. We never identify medication by color. An unreadable or mismatched label requires clinical review; this is not a prescription engine.” |
| 1:25–1:55 | Show failover and caregiver action | “A missing receipt triggers the continuity protocol. Phone-channel delivery is currently blocked by account onboarding, so this screen clearly distinguishes a simulated action from an actual send. The same episode retains the context.” |
| 1:55–2:20 | Pharmacy & audit | “A caregiver can request review. Inventory and appointments are fixtures. Requests remain pending clinician approval, and repeated actions do not duplicate the reservation. A signed payload and PDF preserve the audit trail.” |
| 2:20–2:45 | Switch to Admin & engineering; AWS telemetry | “Here is the runtime evidence: real AWS service responses, request IDs, and execution modes. S3, DynamoDB, Bedrock, EventBridge and an approved SES audit submission were verified. Accepted email is not proof of inbox delivery.” |
| 2:45–3:00 | Architecture and evaluation results | “Our prototype makes continuity and safety decisions inspectable. The next step is phone onboarding and supervised validation; we claim no measured clinical benefit.” |

Do not say “production ready,” “HIPAA compliant,” “prevents readmission,” or “all channels live.” Record the actual state, including any error. Never replace a failed live response with a fabricated success overlay.
