# Audit report `aud-fault-reschedule-double-book`

**Outcome: DISCREPANCIES**

- Call: `call-fault-reschedule-double-book` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 1 | Claim trust score: 100% | Highest severity: `HIGH`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. Rescheduled (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Appointment for Maya Chen from Tue Mar 3 2026, 10:00 AM EST to Thu Mar 5 2026, 11:00 AM EST was moved exactly as claimed.
- **What the caller heard (turn 2):** "I've moved your appointment from Tuesday, March 3 at 10:00 AM to Thursday, March 5 at 11:00 AM."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| new_start | Thu Mar 5 2026, 11:00 AM EST | Thu Mar 5 2026, 11:00 AM EST | yes |
| old_start | Tue Mar 3 2026, 10:00 AM EST | Tue Mar 3 2026, 10:00 AM EST | yes |
| old_slot_released | released | released (same record moved) | yes |
| provider | Dr. Patel | Dr. Patel | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: pass. Side effects are as claimed.

Evidence:
- `calendar` `apt_0001`: Changed by the agent during the call (journal #8; net: updated)

## Findings beyond claims

### F1. POLICY_VIOLATION: `double_booking`

- **Severity:** `HIGH`
- **Finding:** Dr. Patel is double-booked at Thu Mar 5 2026, 11:00 AM EST: apt_0001 (written by the agent) overlaps apt_0002.
- **Fix:** Move one of the two appointments and notify that patient.
- Evidence `calendar` `apt_0001`: Written by the agent during the call
- Evidence `calendar` `apt_0002`: Overlapping appointment with the same provider

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-reschedule-double-book-c1 (Rescheduled): exact match -> apt_0001
7. `verdict` call-fault-reschedule-double-book-c1 (Rescheduled): VERIFIED
8. `policy` double_booking: Dr. Patel is double-booked at Thu Mar 5 2026, 11:00 AM EST: apt_0001 (written by the agent) overlaps apt_0002.
9. `verdict` Outcome: DISCREPANCIES

## Seal

- content `559be1dd4233e17a05e04b420729d630f21fb35694aea66ad82b26533662faad`
- chain `4ec427fd548da74122d39af71288476abce162776bc30df584f37e222f2f57af` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
