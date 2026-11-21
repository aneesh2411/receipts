# Audit report `aud-fault-double-book`

**Outcome: DISCREPANCIES**

- Call: `call-fault-double-book` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 2, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 1 | Claim trust score: 100% | Highest severity: `HIGH`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Extraction: `rules`
- Seal: sha256 chain `f4d1062a4be12af510be5109...`, signed (key `6508b98a7ace`)
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Tue Mar 3 2026, 2:30 PM EST exists exactly as claimed (apt_0002).
- **What the caller heard (turn 2):** "Done. I scheduled your cleaning with Dr. Patel for Tuesday, March 3 at 2:30 PM. I just texted you a confirmation."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550101001) | yes |
| start | Tue Mar 3 2026, 2:30 PM EST | Tue Mar 3 2026, 2:30 PM EST | yes |
| provider | Dr. Patel | Dr. Patel | yes |
| duration | 30 min | 30 min | yes |
| reason | cleaning | cleaning | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The calendar change history for the call window was fully observed.

Evidence:
- `calendar` `apt_0002`: Appointment written by the agent during the call (journal #7; net: created)

### 2. ConfirmationSent (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Confirmation was sent to +15550101001 as claimed (msg_0001).
- **What the caller heard (turn 2):** "Done. I scheduled your cleaning with Dr. Patel for Tuesday, March 3 at 2:30 PM. I just texted you a confirmation."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| recipient | +15550101001 | +15550101001 | yes |
| channel | sms | sms | yes |
| delivery | sent | sent | yes |
| stated_time | Tue Mar 3 2026, 2:30 PM EST | Tue Mar 3 2026, 2:30 PM EST | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The messages change history for the call window was fully observed.

Evidence:
- `messages` `msg_0001`: Message logged during the call (journal #8; net: created)

## Findings beyond claims

### F1. POLICY_VIOLATION: `double_booking`

- **Severity:** `HIGH`
- **Finding:** Dr. Patel is double-booked at Tue Mar 3 2026, 2:30 PM EST: apt_0002 (written by the agent) overlaps apt_0001.
- **Fix:** Move one of the two appointments and notify that patient.
- Evidence `calendar` `apt_0002`: Written by the agent during the call
- Evidence `calendar` `apt_0001`: Overlapping appointment with the same provider

## Audit trail

1. `evidence` calendar: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-double-book-c1 (AppointmentBooked): exact match -> apt_0002
7. `reconcile` call-fault-double-book-c2 (ConfirmationSent): exact match -> msg_0001
8. `verdict` call-fault-double-book-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-fault-double-book-c2 (ConfirmationSent): VERIFIED
10. `policy` double_booking: Dr. Patel is double-booked at Tue Mar 3 2026, 2:30 PM EST: apt_0002 (written by the agent) overlaps apt_0001.
11. `verdict` Outcome: DISCREPANCIES

## Seal

- content `0c3cf9164d9bc0236fd286fd30511f35637444a7a0a68deecfcaf0a67ca6de1a`
- chain `f4d1062a4be12af510be51094a2fd414fc4b7b7108c151b96fb438c5f1243a9f` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
