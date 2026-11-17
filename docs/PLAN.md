# Receipts: plan

> Every claim needs a receipt.

## 1. The problem

Voice AI agents tell callers they did things: "I booked your appointment", "I sent the
confirmation", "I created a ticket". Sometimes none of it happened. The caller hangs up
satisfied, the transcript reads perfectly, and nobody finds out until a patient is standing
at the front desk with no appointment.

The agent's own account cannot settle this. A transcript shows what was said. A tool-call
trace shows what was attempted. Neither shows what the system of record holds now.

## 2. What already exists

I looked before building. Sources are linked; most are vendor or practitioner posts, so treat
them as claims about positioning, not independent benchmarks.

**Voice agent QA platforms** (Hamming, Coval, Cekura, Roark, Bluejay). These simulate calls
before launch and monitor production calls afterwards. Their unit of analysis is the
conversation: audio, transcript, latency, whether the agent followed the script. See for
example [Hamming vs Coval](https://hamming.ai/blog/hamming-vs-coval). They answer "did the
agent behave well on the call". They do not read the clinic's calendar.

**In-path tool receipts.** The tool layer writes a receipt when a tool executes, and claims
are checked against those receipts
([channel.tel](https://www.channel.tel/blog/tool-receipts-agent-tool-call-verification)).
This works, but it requires instrumenting the agent, and it trusts the agent's own tool layer
to be the witness.

**Post-condition probes.** After the agent says "done", re-query the target system and check
that something matching exists
([tianpan.co](https://tianpan.co/blog/2026-04-23-hallucinated-success-agent-false-completion),
[dev.to](https://dev.to/adriencr81/how-do-you-verify-what-your-ai-agent-actually-did-3f9f)).
This is the closest idea. Its known weakness is that "something matching exists" is not the
same as "the agent did what it said": a state lookup passes a booking that existed before
the call, and says nothing about writes the agent never mentioned. A recent preprint makes
the same point about damage outside the goal's scope
([arXiv 2608.15286](https://arxiv.org/pdf/2608.15286)).

I did not find a product that reconciles an agent's claims against the system of record's
own change history, in both directions, per call. That is the gap this project targets.

## 3. The product, and why each decision

| Decision | Why it makes the product better |
|---|---|
| **Out of band.** Evidence comes from the system of record's change feed, never from the agent. | No agent instrumentation, works with any vendor's agent, and the witness is independent of the suspect. |
| **Change history, not current state.** Verify against what changed during the call window. | Catches credit taken for a pre-existing record, and writes that were made then undone. A state lookup cannot. |
| **Two directions.** Claims are checked against writes, then writes against claims. | The second direction finds unclaimed writes: the damage an agent never mentions. |
| **Two claim sources.** Structured claims plus what the caller was actually told. | The spoken promise is the real contract. An agent that says "booked" and logs nothing leaves no structured claim to check. |
| **No model on the verdict path.** Verdicts are deterministic joins with evidence attached. | An auditor that can hallucinate is not an auditor. A model may help read a transcript; it never decides what is true. |
| **Four verdicts, including UNVERIFIABLE.** | When a system is unreachable the auditor says so. A guessed verdict is worse than none. |
| **Severity by caller impact, with a fix.** | "NOT_FOUND" is a finding. "Patient will show up to nothing; create the booking or call back" is something an operator can act on. |
| **Sealed, hash-chained reports.** | An audit trail that can be edited quietly is not an audit trail. |
| **The auditor is audited.** Golden set, fuzzing, a naive baseline, ablations. | The claim "it catches lies" needs its own receipt. |

## 4. Scope of this build

In scope:

1. **The suspect**: a simulated dental receptionist with 22 tunable fault modes (the six
   required, plus sixteen found by asking "how else could this go wrong").
2. **System of record**: SQLite behind adapter interfaces for calendar, CRM, message log and
   ticket queue, with a trigger-written, append-only change journal.
3. **The auditor**: reconciliation, per-claim verdicts with evidence, unclaimed-write and
   policy findings, a per-call audit trail, sealed reports.
4. **Evals**: 52 hand-labelled scenarios, a fuzz generator, a scoring runner, a naive
   baseline, ablations, and a failure analysis.
5. **API**: FastAPI with `POST /calls`, `POST /audit`, `GET /audit/{id}/report`, plus ledger
   verification, a scorecard and a demo sandbox.
6. **Demo**: a CLI replay and a browser replay view with claim and evidence side by side.

Out of scope for now: live telephony, real CRM / SMS adapters (the
interface is in place, and Google Calendar is implemented), multi-tenant auth, rate limiting.

## 5. Build order

1. Typed models for claims, records, verdicts.
2. System of record with the journal. Everything else depends on trustworthy evidence.
3. The suspect and its fault modes.
4. The auditor, written against the read-only adapter interfaces.
5. Golden scenarios with hand-written labels; scorer; baseline.
6. Fuzzing, to check results do not depend on hand-picked conditions.
7. API, CLI, replay view.
8. Failure analysis from real results.

## 6. Risks and how they are handled

| Risk | Handling |
|---|---|
| Suspect and auditor share a bug, so tests pass for the wrong reason. | Golden labels are written by hand, not derived from suspect code. A naive baseline and ablations show the eval can tell good from bad. |
| Eval is too easy because the suspect's phrasing is templated. | Stated plainly in the failure analysis. Vague phrasing is included as a known gap and counted against recall. |
| Attribution: a real system of record does not know which call caused a write. | Attribution uses the agent's integration identity plus the call window. Writes by other actors in the window are ignored. Limits are documented. |
| False accusations erode trust faster than misses. | Precision is tracked separately and gated in CI. Outages yield UNVERIFIABLE, never an accusation. |
