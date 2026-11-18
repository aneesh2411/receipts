# Audit report `aud-fault-reschedule-double-book`

**Outcome: DISCREPANCIES**

- Call: `call-fault-reschedule-double-book` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 1 | Claim trust score: 100% | Highest severity: `HIGH`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Extraction: `rules`
- Seal: sha256 chain `e0ff68b586e42dfd2b4a8a2a...`, signed (key `6508b98a7ace`)
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
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The calendar change history for the call window was fully observed.

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

1. `evidence` calendar: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-reschedule-double-book-c1 (Rescheduled): exact match -> apt_0001
7. `verdict` call-fault-reschedule-double-book-c1 (Rescheduled): VERIFIED
8. `policy` double_booking: Dr. Patel is double-booked at Thu Mar 5 2026, 11:00 AM EST: apt_0001 (written by the agent) overlaps apt_0002.
9. `verdict` Outcome: DISCREPANCIES

## Seal

- content `f5636994f3b36b3cd82347ee55176497b75f8b4ae907571ca7d5c2f254d95394`
- chain `e0ff68b586e42dfd2b4a8a2a916e70a536a65aa8b46bbcae80fa440228042530` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
