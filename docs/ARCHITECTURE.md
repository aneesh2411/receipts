# Architecture

## Shape

```
                 writes                          reads only
  +-----------+ ---------> +------------------+ <--------- +-----------+
  |  Suspect  |            | System of record |            |  Auditor  |
  |  (agent)  |            |  calendar | CRM  |            |           |
  +-----------+            |  messages | tix  |            +-----------+
        |                  |  + change journal|                  |
        | CallRecord       +------------------+                  | AuditReport
        | (transcript + claims)                                  | (sealed)
        +--------------------------> POST /calls, /audit <-------+
```

Three parties, two trust levels:

- The **suspect** is untrusted. Everything it hands over (transcript, claims) is a claim.
- The **system of record** is ground truth. Its change journal is written by database
  triggers, not by application code, so the suspect cannot skip it or forge it.
- The **auditor** holds a read-only handle. It is typed against `*Reader` protocols and
  cannot write to the systems it audits.

## Packages

| Package | Responsibility |
|---|---|
| `receipts.models` | Frozen pydantic models: claims, records, verdicts, report. |
| `receipts.sor` | Adapter protocols, SQLite implementation, Google Calendar stub. |
| `receipts.suspect` | The receptionist, its narrator, fault modes and fault plans. |
| `receipts.auditor` | Extraction, reconciliation, verdicts, findings, sealing, rendering. |
| `receipts.scenarios` | Golden dataset and the deterministic world that plays a scenario. |
| `receipts.evals` | Scorer, fuzz generator, eval runner and report. |
| `receipts.api` | FastAPI service, audit ledger, replay view. |
| `receipts.llm` | The single interface a language model comes through. Optional. |

## The system of record

Each domain has a reader protocol (lookups plus `changes(since, until)`) and an adapter
protocol that adds writes. One requirement makes a backend auditable: it can answer **"what
changed between t0 and t1, and who changed it?"**

The SQLite implementation records that in `change_log`:

- Written by `AFTER INSERT / UPDATE / DELETE` triggers on every audited table.
- Each row carries before and after images, the actor and the time.
- Append-only: triggers abort any `UPDATE` or `DELETE` on the journal.

For Google Calendar the same contract maps to `events.list(updatedMin, showDeleted)` plus a
snapshot cache for before-images. See `sor/google_calendar.py`.

## The auditor pipeline

```
 1 collect claims    structured  +  recovered from transcript
 2 pull evidence     change feed per system, call window, agent's identity
 3 net changes       create+delete = nothing; edit+revert = nothing
 4 reconcile         strict pass (exact), then loose pass (best partial)
 5 judge             field-by-field diff -> verdict + evidence + severity
 6 reverse           writes left over -> UNCLAIMED_WRITE
 7 policy            double booking, closed hours, past dates
 8 seal              content hash -> ledger chain -> HMAC
```

### 1. Claims

Structured claims are what the agent logged. The transcript extractor recovers what the
agent *told the caller*. A spoken claim is dropped when a structured claim in the same turn
describes the same commitment; otherwise it is audited as a claim in its own right. This is
how "said booked, logged nothing" and "logged 2:30, told the caller Wednesday" are caught.

The extractor sits behind `ClaimExtractor`. The default is rule-based and offline. A
model-backed extractor exists for vague phrasing; its output is schema-validated and it
falls back to the rules on any failure.

### 2-3. Evidence

For each system the auditor pulls the journal for `[call start, call end + grace]`, keeps
rows whose actor is the agent's integration identity, and reduces them to **net changes**
per record: created, updated, deleted, or transient (no net effect).

Attribution is by identity and time, not by call id, because a real calendar has never
heard of a call id. Writes by other actors in the window (front-desk staff) are ignored.

### 4. Reconciliation

Each claim type has a matcher that scores candidate writes. Two passes:

1. **Strict.** Every claim takes a write that matches it exactly, if one exists.
2. **Loose.** Remaining claims take the best partial match: same patient, or same slot
   under another name.

Exact matches going first matters. Without it, a claim with a wrong time could grab the
write that belongs to a different, correct claim in the same call.

A matched write is consumed. A claim with no match has no receipt.

Reschedules are matched as one of three shapes: moved in place, released and re-created, or
released and never replaced.

### 5. Verdicts

| Status | Meaning |
|---|---|
| `VERIFIED` | The claimed action happened in this call, exactly as claimed. |
| `MISMATCH` | Something happened, but not what was claimed. |
| `NOT_FOUND` | No evidence the action happened in this call. |
| `UNVERIFIABLE` | The evidence could not be read. No guess is made. |

Every verdict carries three checks (`existence`, `exactness`, `side_effects`), a
claimed-versus-actual table, the evidence records, a severity based on caller impact, and a
suggested fix.

### 6-7. Findings beyond claims

- **Unclaimed writes.** Any net change by the agent that no claim consumed. A new patient
  record implied by a booking claim is treated as a supporting write, not a finding. If a
  claim that might own a write could not be verified, the check for that system is skipped:
  an outage must not manufacture an accusation.
- **Policy violations.** Pluggable `Policy` objects run over every appointment the agent
  placed: double booking, outside business hours, in the past.

### Outcome

`DISCREPANCIES` if any claim is false or any finding exists. Otherwise `INCONCLUSIVE` if
any system could not be read (it may be hiding unclaimed writes). Otherwise `CLEAN`.

### 8. Sealing

`content_hash` is SHA-256 over the report's canonical JSON. `chain_hash` links it to the
previous report in the ledger. With `RECEIPTS_SIGNING_KEY` set, the chain hash is signed
with HMAC-SHA256. The ledger table is append-only, and `GET /ledger/verify` re-checks every
seal and link, starting from genesis.

Without a key, a seal detects accidental or naive edits but can be recomputed by anyone.
With a key, a forged seal fails verification.

## Determinism

- The suspect runs on a simulated clock. Record ids come from per-entity counters.
- Narrator phrasing is drawn from an RNG seeded with the scenario id.
- The audit timestamp is derived from the call. Playing a scenario twice produces
  byte-identical calls, reports and seals. Tests assert this.

## Extension points

| To add | Implement |
|---|---|
| A real calendar, CRM, SMS provider | the matching `*Reader` protocol in `sor/base.py` |
| A new claim type | a model in `models.py` and a `match` / `judge` pair in `auditor/` |
| A clinic rule | a `Policy` in `auditor/findings.py` |
| A better transcript reader | a `ClaimExtractor` |
| A different model vendor | an `LLMClient` |

## Known limits

- **Attribution** assumes the agent writes under its own identity. If the agent shares
  credentials with humans, writes cannot be told apart.
- **Overlapping calls** by the same agent identity share a window. A write is consumed by
  whichever call's claim matches it; a write that matches no claim would be reported
  against every call whose window covers it.
- **Free text** (ticket summaries) is not compared.
- **Current-state checks** (zombie appointments, double booking) read state at audit time.
  Audit soon after the call.
