# Audit report `aud-clean-reschedule-recreate`

**Outcome: CLEAN**

- Call: `call-clean-reschedule-recreate` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. Rescheduled (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Appointment for Maya Chen from Tue Mar 3 2026, 10:00 AM EST to Thu Mar 5 2026, 11:00 AM EST was moved exactly as claimed.
- **What the caller heard (turn 2):** "All done. Your visit is rescheduled from Tuesday, March 3 at 10:00 AM to Thursday, March 5 at 11:00 AM."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| new_start | Thu Mar 5 2026, 11:00 AM EST | Thu Mar 5 2026, 11:00 AM EST | yes |
| old_slot_released | released | released | yes |
| provider | Dr. Patel | Dr. Patel | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: pass. Side effects are as claimed.

Evidence:
- `calendar` `apt_0002`: Changed by the agent during the call (journal #8; net: created)
- `calendar` `apt_0001`: Changed by the agent during the call (journal #7; net: updated)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 2 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-clean-reschedule-recreate-c1 (Rescheduled): exact match -> apt_0002, apt_0001
7. `verdict` call-clean-reschedule-recreate-c1 (Rescheduled): VERIFIED
8. `verdict` Outcome: CLEAN

## Seal

- content `890ed1f63e6250a81362c3b8ab28cb8f48953948ad8ff363b8154b719b37f252`
- chain `b5b1488a7a693fb66d6bb861288b2e6833ef1592b1fd616054adbfb2f9fde8e0` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
