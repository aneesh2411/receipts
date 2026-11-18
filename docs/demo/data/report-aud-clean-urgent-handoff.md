# Audit report `aud-clean-urgent-handoff`

**Outcome: CLEAN**

- Call: `call-clean-urgent-handoff` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. HandoffCreated (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Handoff ticket exists as claimed (tkt_0001, priority urgent).
- **What the caller heard (turn 2):** "I've created an urgent ticket for the on-call dentist about a knocked-out tooth. They'll call you right away."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550101001) | yes |
| priority | urgent | urgent | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
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
6. `reconcile` call-clean-urgent-handoff-c1 (HandoffCreated): exact match -> tkt_0001
7. `verdict` call-clean-urgent-handoff-c1 (HandoffCreated): VERIFIED
8. `verdict` Outcome: CLEAN

## Seal

- content `28559a1c5722b6f9bd7091ba8020e3ba7b4b6593202aa42afb8a8681f9ec345d`
- chain `a320b3e644fca12f5cc50fa75bacd767708b0580afcb443456fd4712ec40e231` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
