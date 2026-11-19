# Research: what a complete outcome auditor needs

Written 2026-11-19 to decide what to build next. Method: read what the adjacent
products actually ship (their own pages, cited below), find the gap Subpoena
fills, then pick the next features so the gap becomes a product instead of a
demo. No claims here about competitor internals; only what their public pages
say.

## 1. The landscape

**Voice-agent pre-production testing.** Hamming (hamming.ai/product/automated-testing)
generates test scenarios from the agent's prompt, replays production calls as
test cases, simulates languages, accents, noise and load (50K+ concurrent
calls). Cekura (cekura.ai) does pre-production simulation, cross-platform
benchmarking (Vapi vs Retell vs ElevenLabs), adversarial red-teaming, and a
self-improving loop: flag a failure, reproduce it in simulation, patch the
prompt, re-run the gate. Both verify with model-based analysis of the
conversation. Hamming's own marketing figure is Subpoena's core case: the agent
says "You're booked for Tuesday at 3" and nothing was booked.

**Contact-center QA for human agents.** Observe.AI (observe.ai/post-interaction/auto-qa)
auto-scores 100% of interactions against scorecards, with calibration tooling
and - notably - agent acknowledgement and dispute options: a scored human can
challenge the QA result. CallMiner (callminer.com) ingests 100% of
conversations, blends weighted characteristics into review-ranking scores, and
leans on compliance certifications (FISMA, PCI, HITRUST). Both score human
agents for coaching; neither checks whether a promised write happened.

**Agent trajectory evaluation.** LangChain's agentevals (docs.langchain.com/langsmith/trajectory-evals)
verifies an agent's tool-call trajectory against a reference, in strict /
unordered / subset / superset modes - deterministic, or an LLM judge when
determinism is not available. This is the closest conceptual neighbor: compare
what the agent did against what it should have done. It is a pre-deployment
dev tool, generic across agent types, with no business-outcome semantics, no
production ledger, and no evidence a reviewer can check.

## 2. The gap Subpoena fills

All three categories stop short of the production outcome:

- Pre-production tools (Hamming, Cekura) ask "will the agent behave?" before
  go-live. Subpoena asks "did it actually do what it said?" on every real call,
  after the fact, against the system of record.
- QA tools (Observe.AI, CallMiner) score conversation quality for coaching.
  Subpoena produces verdicts about commitments, with evidence.
- Trajectory evals check tool calls against a reference in a test harness.
  Subpoena reconciles claims against the real journal of the real calendar,
  CRM, messages and tickets, and seals the result so it cannot be quietly
  edited later.

The differentiators worth pressing, because nobody in the landscape combines
them: deterministic verdicts with no model on the verdict path, evidence on
every verdict, tamper-evident sealed ledger, and attribution strength when one
agent identity handles overlapping calls.

## 3. What a complete product needs that this repo does not have

Ranked by how much they close the gap between demo and product:

1. **Ingest from a real voice platform.** Today every call is simulated or
   hand-built. A complete product eats real end-of-call payloads. Twilio Voice
   first: it is the largest platform, the payload shape is public, and the
   outcome-audit story lands hardest where answering-machine detection is known
   to be blind. A webhook receiver turns a Twilio status callback plus
   transcription into a `CallRecord` with platform provenance, auditable like
   any other call. Offline: fixtures are recorded payloads, tests need no
   network.
2. **A review workflow for discrepancies.** Every QA product that humans rely
   on has one: the flagged item becomes a task someone can acknowledge,
   resolve, or dispute (Observe.AI's dispute flow is the model). Subpoena's
   version fits the ledger story: findings become review items with owners and
   state transitions, and every transition is itself journaled and sealed.
   "Every claim needs a receipt" extends to "every verdict can be challenged,
   and the challenge gets a receipt."
3. **Honesty over time.** The `/scorecard` endpoint answers "how honest is
   this agent?" A complete product answers "did it get worse when the prompt
   changed?" Provenance already carries agent version; the missing piece is a
   time series per agent version and claim type, so a regression is visible
   the day it ships.
4. **Alerting on critical findings.** A critical finding should reach a human
   fast. Generic outbound webhook on critical findings (user-configured URL,
   no third-party service) covers it; everything heavier waits.

Deliberately deferred: multi-tenant auth and retention (real, but it is
plumbing that demos badly), and more claim types (payments, records updates)
until ingest exists to feed them real data.

## 4. What practitioners ask for (LinkedIn research, 2026-11-19)

A sourced read of practitioner discussions (vendors and buyers of voice AI;
failure rates self-reported, feature ranking is inference) lines up behind the
same gap and sharpens the wave:

1. "The agent said it booked; the calendar says otherwise" is the recurring
   pain (calendar API 429s during peak, then a confident confirmation; evals
   showing a tool call but no event created). This is Subpoena's core case.
2. Corrections must bind to the final write: a caller correcting Thursday to
   Tuesday must result in Tuesday on the record, with the stale value nowhere
   reappearing - acknowledging the correction is not using it. New audit
   capability: correction-aware claim chains (#TBD).
3. Handoff success is context delivery, not a transfer attempt (a 69-comment
   CX thread). This is our known gap gap-garbled-handoff: free-text ticket
   summaries are where it bites.
4. Every flag must be reviewable, and confirmed failures should become
   regression cases tied to the agent version - supports #49 and #50.
5. Transparent audit cost and a cheap test mode - cheap to keep in mind for
   the API, not a feature yet.

Sources: linkedin.com posts by Pritesh Kumar (Dograh), Vadym Marochok,
Sajid Manzoor (Testiva), Nishant Sinha, Noreen Javed, Nick Brezonik,
Mike Oeth, Antaripa Saha, Alex Pricopie, Skylar Bays, Frank Kish;
parlance-labs.com/blog/posts/auto-evals. Retrieved 2026-11-19.

## 5. The wave

Sequenced so each piece lands independently:

1. Twilio ingest receiver (#TBD) - new module, no auditor-core changes.
2. Reconcile by assignment instead of claim order (#39) - lets same-kind
   multi-intent calls into the fuzzer; prerequisite for trusting verdicts on
   real messy calls.
3. v2 semantic scorer (#42) - reviewed identity labels, dual-run with
   positional v1, historical cards preserved.
4. Review workflow for findings (#TBD) - data model, transitions, sealed
   journal, API.
5. Honesty-over-time scorecards (#TBD) - per agent version and claim type.
6. Critical-finding webhook (#TBD) - last, smallest.
7. Correction binding (#TBD) - the last settled value must be what lands in
   the write, for date, patient, phone and recipient claims.

## Sources

- hamming.ai/product/automated-testing
- cekura.ai
- observe.ai/post-interaction/auto-qa
- callminer.com/compare/callminer-vs-observe-ai
- docs.langchain.com/langsmith/trajectory-evals

(retrieved 2026-11-19)
