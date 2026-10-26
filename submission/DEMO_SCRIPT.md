# Three-minute judge demonstration

Open https://pulsecontinuum.vercel.app without signing in. Use **Care team** first. The three case cards load clearly labeled recorded AWS inference; they do not pretend to run a fresh model request. Every human entry below is explicitly a synthetic role-play. Phone delivery and outbound email remain disabled.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:20 | Overview and three recorded cases | “The problem is a lost care handoff after discharge. We preserve the written plan, patient evidence and next action in one episode.” |
| 0:20–0:45 | Post-surgery case: Explore recorded case | “This is recorded AWS test evidence, not a fresh inference. A medication label does not override reported warning symptoms. The app has not stopped or changed the prescription.” |
| 0:45–1:05 | Request clinician review; step 4 | “The next action is assessment, not buying tablets. Medication delivery and routine-plan clearance are blocked in this symptomatic case.” |
| 1:05–1:40 | Review & follow-up: synthetic decision and teach-back | “The human decision is explicit. This role-play requests treating-team assessment; the patient or caregiver then states their understanding. We do not automatically mark that understanding as verified.” |
| 1:40–2:00 | Follow-up record and doctor handoff packet | “A contact record is not proof of recovery. The PDF/email format carries the report, review reason, decision and pending follow-up. The hosted packet is generated, not emailed.” |
| 2:00–2:25 | Briefly contrast wound case and caregiver-fallback case | “An unrelated medication label stays a discrepancy. With data loss, the caregiver retains the same assessment context. Phone messages are previews, clearly NOT_SENT.” |
| 2:25–2:45 | Admin & engineering | “The bounded Python workflow runs on Lambda, uses Nova Pro for evidence interpretation and deterministic gates for permitted actions. Original model request evidence and current SDK activity are distinguished; this is not a deployed managed AgentCore system.” |
| 2:45–3:00 | Validation summary | “Three live AWS pathways passed 28 scenario checks, and 23 regression tests pass. These are engineering results, not evidence of medical accuracy or clinical benefit.” |

Suggested synthetic form entries:

- Review: “SYNTHETIC EXAMPLE: Reviewed the report and requested treating-team assessment; the app makes no medicine change.”
- Teach-back: “SYNTHETIC EXAMPLE: I understand the clinical team must assess the report. The app has not changed my medicine plan.”
- Follow-up: “SYNTHETIC EXAMPLE: The follow-up conversation was recorded; assessment and recovery remain unverified.”

Prefer one complete story over a rushed tour of all five pages. Use the other two cases to establish that the safeguards survive different inputs and a communication failure. Never describe recorded inference as fresh, a preview as handset delivery, a generated packet as sent email, or a synthetic clinician note as a real consultation.
