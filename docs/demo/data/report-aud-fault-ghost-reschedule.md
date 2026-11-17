# Audit report `aud-fault-ghost-reschedule`

**Outcome: DISCREPANCIES**

- Call: `call-fault-ghost-reschedule` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 1, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `HIGH`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

## Claims

### 1. Rescheduled (logged claim): RECEIPT DOES NOT MATCH

- **Status:** `MISMATCH` | **Severity:** `HIGH`
- **Finding:** The calendar changed, but not the way the caller was told. old_appointment: claimed Tue Mar 3 2026, 10:00 AM EST, actual nothing was ever booked then.
- **What the caller heard (turn 2):** "All done. Your visit is rescheduled from Tuesday, March 3 at 10:00 AM to Thursday, March 5 at 11:00 AM."
- **Fix:** Reconcile the calendar with what the caller was told: one appointment, at the promised time, and the old slot released.

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| new_start | Thu Mar 5 2026, 11:00 AM EST | Thu Mar 5 2026, 11:00 AM EST | yes |
| old_appointment | Tue Mar 3 2026, 10:00 AM EST | nothing was ever booked then | **NO** |
| old_slot_released | released | released | yes |
| provider | Dr. Patel | Dr. Patel | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: FAIL. Differs on: old_appointment.
- `side_effects`: pass. Side effects are as claimed.

Evidence:
- `calendar` `apt_0001`: Changed by the agent during the call (journal #6; net: created)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-ghost-reschedule-c1 (Rescheduled): exact match -> apt_0001
7. `verdict` call-fault-ghost-reschedule-c1 (Rescheduled): MISMATCH
8. `verdict` Outcome: DISCREPANCIES

## Seal

- content `0646ce96a7bc3fc985f76ac32113659edeeeb6ec0c69470e309ccd61342c5c08`
- chain `230ecbe247fb4c7ca0f12378c2b2c1961d5c3dae085a2d9b88cd2154d4bbb8b3` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
