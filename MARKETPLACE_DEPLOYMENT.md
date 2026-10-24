# AWS Partner Marketplace business case

## Buyer and outcome

Target hospital care-transition teams and payer-sponsored post-discharge programs. The offering coordinates patient outreach, medication-evidence review, caregiver continuity, and physician audit packets. The purchasing unit is a monitored recovery episode, with a monthly platform minimum. Care decisions remain under licensed clinician authority.

## Proposed listing and delivery

Offer a SaaS contract with a private-offer pilot and a customer-owned AWS data plane. Use Marketplace entitlement and metering integration before commercial launch; those integrations are not implemented in this demo. Provision data resources using the supplied CDK. Deploy the API and Next.js containers behind authenticated TLS ingress, and configure messaging and clinical integrations separately. An optional existing AgentCore runtime can participate via its ARN. Customer onboarding includes consent, contact verification, phone/RCS registration, SES verification, model access, operational monitoring, and clinician sign-off.

## Illustrative unit economics (not AWS price quotes)

Assume 1,000 episodes per month at $12 per episode, with 20 messages and two multimodal analyses per episode. These are planning assumptions to replace with region-, carrier-, model-, and volume-specific estimates.

| Item | Assumed cost per episode |
| --- | ---: |
| Messaging and email | $0.80 |
| Model inference and guardrail calls | $0.45 |
| Storage, orchestration, logging and compute | $0.35 |
| Allocated operational support | $1.40 |
| Total illustrative variable cost | $3.00 |
| Revenue | $12.00 |
| Contribution before fixed overhead and fees | $9.00 / 75% |

Monthly modeled revenue is $12,000, variable cost $3,000, and contribution $9,000 before Marketplace fees, sales, fixed engineering, compliance, tax, and clinical labor. Sensitivity: doubling messaging and inference costs reduces contribution to $7.75 per episode. There is no claim that these figures are current AWS service prices or demonstrated hospital savings.

## Pilot acceptance

Measure acknowledged outreach, time to clinician review, caregiver response, verified-label rate, false-positive triage burden, and episode-level continuity. Compare utilization outcomes using a pre-agreed evaluation design; do not equate a message sent or a model risk score with a prevented readmission. Set budget alerts, cost allocation tags, bounded retention, and per-episode service limits.

## Release gates

Commercial deployment requires tenant isolation, authenticated clinician access, reliable event normalization, messaging consent and opt-out controls, healthcare data handling agreements, integration validation, a real ERP and scheduling provider, managed service deployment/observability, and clinical safety evaluation. The supplied software is an MIT hackathon demonstration, not an already approved Marketplace listing.
