# Audit report `aud-clean-cancel`

**Outcome: CLEAN**

- Call: `call-clean-cancel` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. Cancelled (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Appointment for Maya Chen on Tue Mar 3 2026, 10:00 AM EST was cancelled as claimed (apt_0001).
- **What the caller heard (turn 2):** "Your appointment on Tuesday, March 3 at 10:00 AM is now cancelled."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| start | Tue Mar 3 2026, 10:00 AM EST | Tue Mar 3 2026, 10:00 AM EST | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The calendar change history for the call window was fully observed.

Evidence:
- `calendar` `apt_0001`: Released by the agent during the call (journal #7; net: updated)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-clean-cancel-c1 (Cancelled): exact match -> apt_0001
7. `verdict` call-clean-cancel-c1 (Cancelled): VERIFIED
8. `verdict` Outcome: CLEAN

## Seal

- content `fc72e7fceb254fc642f507fc06835566220ff563bf96c8ab581e6752d1c2c522`
- chain `df14516a2a6288f4633fa8445a19641bad2bc36644b5f5640918dbbf7b45b6f9` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
