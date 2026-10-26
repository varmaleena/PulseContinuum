# Patient-journey validation — 26 October 2026

## What was wrong

The earlier prototype demonstrated a technical chain, not a complete information handoff. After analysis it displayed generic pharmacy choices and ended at a pending request plus an email/PDF. There was no recorded clinician response, patient acknowledgment or follow-up. Pill color also incorrectly contributed to a named-NSAID rule, and a simple negated fever statement could trigger the fallback warning rule.

## Corrected workflow

| Step | Actor in the demonstration | What the app records | What it does not establish |
| --- | --- | --- | --- |
| Written plan | Discharge/care coordinator | Explicit medication rows and synthetic follow-up context | A new prescription |
| Report and evidence | Synthetic patient + Bedrock analysis | Reported symptoms, label evidence, uncertainty and review signal | Diagnosis, clinical suitability or validated readmission probability |
| Review request | Patient or caregiver | An idempotent clinical handoff; optional fallback preview | Medicine dispensing, appointment booking or actual phone delivery |
| Review decision | Demonstrator playing a clinician | A labeled synthetic assessment/reconciliation decision and notes | A real clinician consultation or authorization |
| Teach-back | Demonstrator playing patient/caregiver | Their entered words and actor | Automatically verified understanding |
| Follow-up | Care-coordinator role | Contact note or reassessment request | Verified recovery or completion of real medical care |

The email/PDF is the **handoff record** containing the written plan, patient report, review reason, decision, acknowledgment and follow-up. It is not the treatment. Updating the packet does not resend email. Hosted outbound channels remain disabled.

## Three live AWS pathways

| Synthetic case | Distinct failure mode | Checks passed | Observed analysis-request latency |
| --- | --- | --- | --- |
| EP-2026-409: postoperative fever and uncertain tablet | Medication evidence must not override symptoms | 9 | 2,847.3 ms |
| EP-2026-425: wound deterioration and unrelated label | Out-of-formulary evidence must not create a medicine order | 9 | 2,340.5 ms |
| EP-2026-429: breathlessness and caregiver fallback | Handoff context must survive a simulated channel loss | 10 | 2,742.0 ms |

These are single observed HTTP timings for synthetic test runs, including the workflow request; they are not benchmarks, clinical response times or SLAs.

The hosted tests made **three actual Bedrock analyses**, checked **46 HTTP responses**, and passed **28 scenario assertions**. Each checked validated model output, prohibited generic/brand delivery, unchanged written medications, enforced review/acknowledgment order, an updated payload hash and PDF, no fabricated recovery, no outbound email and replay without another inference allowance decrement. The fallback case also checked distinct patient/caregiver messages labeled NOT_SENT.

[Machine-readable results](high-risk-journey-results.json) · [Reproducible hosted test](../tools/validate_high_risk_journeys.py)

## Regression coverage

The backend suite passes 23 tests. New coverage includes the three pathway variants, two follow-up outcomes, idempotent review records, rejection of routine-plan clearance for warning symptoms, stale-handoff prevention, negated symptom statements, color not establishing NSAID identity and text-only output not proving a readable label. The existing suite also covers schema failure, authentication, malformed uploads, receipts, timeout behavior, storage recovery and cost-limit rejection.

Recorded-case exploration is explicitly labeled **RECORDED_AWS_RUN**. It retrieves the original AWS test evidence and permits new synthetic handoff actions; it does not invent a fresh model request or a delivery receipt.

## Clinical and usability boundaries

This verifies engineering behavior, not clinical efficacy, safety certification, clinical triage accuracy or appropriateness for real patients. Symptom keyword rules and a model review signal are not a validated medical triage system. Free-text teach-back still requires human interpretation. The public demonstration is shared synthetic state, not patient tenancy or hospital SSO.

The workflow structure is informed by the importance of medication reconciliation, patient/family understanding and follow-up in [AHRQ's discharge-planning guidance](https://www.ahrq.gov/patient-safety/patients-families/engagingfamilies/strategy4/index.html). This is not a claim of AHRQ approval or compliance.

## Additional browser-review findings

The walkthrough also exposed provenance and stale-evidence issues: fresh analysis could inherit the recorded-case marker, and a discharge plan could be replaced beneath an existing analysis. Fresh analysis now clears replay provenance, and replacing an analyzed plan requires an explicit synthetic reset. A dedicated regression test covers both. The care view emphasizes categorical assessment needs instead of displaying an unvalidated model risk number; raw technical evidence remains available.

The caregiver message now requests medication review or clinician assessment rather than “nurse + meds,” and includes a short excerpt of the patient report plus the episode identifier. Follow-up cases requesting reassessment stay visible in the open-handoff queue. Framework/security verification is recorded separately in `production-dependency-audit.json` and the root verification log.

## Final public deployment verification

All three recorded scenarios also passed the complete public Vercel proxy journey without credentials and without new model requests. The first two ended at FOLLOW_UP_RECORDED; the caregiver case ended at REASSESSMENT_REQUIRED. Both public view profiles were reachable. See public-journey-results.json and tools/validate_public_demo.py. One complete handoff was exercised manually in the browser; the other scenario launches and distinct evidence were visually inspected. This does not claim three independent manual browser walkthroughs.
