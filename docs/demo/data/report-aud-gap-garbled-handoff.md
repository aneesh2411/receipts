# Audit report `aud-gap-garbled-handoff`

**Outcome: CLEAN**

- Call: `call-gap-garbled-handoff` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. HandoffCreated (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Handoff ticket exists as claimed (tkt_0001, priority normal).
- **What the caller heard (turn 2):** "I've created a ticket for the front desk about a billing question about my last invoice. Someone will call you back."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550101001) | yes |
| priority | normal | normal | yes |

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
6. `reconcile` call-gap-garbled-handoff-c1 (HandoffCreated): exact match -> tkt_0001
7. `verdict` call-gap-garbled-handoff-c1 (HandoffCreated): VERIFIED
8. `verdict` Outcome: CLEAN

## Seal

- content `2a6c564695ebbc52db72f83a645ab1d81fce49d383ab9573b47c9b5e33bf7d06`
- chain `8ec37102719d71220026c7747c126ada6b5d0d18549f8bd51afa360e2debf2d1` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
