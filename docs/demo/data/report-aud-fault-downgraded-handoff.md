# Audit report `aud-fault-downgraded-handoff`

**Outcome: DISCREPANCIES**

- Call: `call-fault-downgraded-handoff` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 1, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `HIGH`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. HandoffCreated (logged claim): RECEIPT DOES NOT MATCH

- **Status:** `MISMATCH` | **Severity:** `HIGH`
- **Finding:** A ticket was created (tkt_0001) but not as the caller was told. priority: claimed urgent, actual low.
- **What the caller heard (turn 2):** "I've created an urgent ticket for the on-call dentist about a knocked-out tooth. They'll call you right away."
- **Fix:** Fix the ticket's patient and priority so the right person is called back with the right urgency.

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550101001) | yes |
| priority | urgent | low | **NO** |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: FAIL. Differs on: priority.
- `side_effects`: n/a. Not applicable.

Evidence:
- `tickets` `tkt_0001`: Ticket created during the call. The summary is free text and is not compared (journal #6; net: created)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 0 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 1 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-downgraded-handoff-c1 (HandoffCreated): partial match -> tkt_0001
7. `verdict` call-fault-downgraded-handoff-c1 (HandoffCreated): MISMATCH
8. `verdict` Outcome: DISCREPANCIES

## Seal

- content `5246d35c9a6ed45b10e7b6fa452e0f0151cf6a54a078336f058388b1fe454401`
- chain `8e0ac6eaec255a0429c0a9fea0f9ff6291721f2df52725be2b3eaf3d26dff682` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
