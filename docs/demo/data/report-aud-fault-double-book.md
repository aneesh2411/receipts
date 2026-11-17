# Audit report `aud-fault-double-book`

**Outcome: DISCREPANCIES**

- Call: `call-fault-double-book` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 2, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 1 | Claim trust score: 100% | Highest severity: `HIGH`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

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

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 1 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-double-book-c1 (AppointmentBooked): exact match -> apt_0002
7. `reconcile` call-fault-double-book-c2 (ConfirmationSent): exact match -> msg_0001
8. `verdict` call-fault-double-book-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-fault-double-book-c2 (ConfirmationSent): VERIFIED
10. `policy` double_booking: Dr. Patel is double-booked at Tue Mar 3 2026, 2:30 PM EST: apt_0002 (written by the agent) overlaps apt_0001.
11. `verdict` Outcome: DISCREPANCIES

## Seal

- content `3d586db8b456d0e60160f68efbf72c65c7d219cf51f3c7800d13fac7ae794a51`
- chain `a7deb1c158ad1b10f444eb02d34fab0f2892e693f4172d305d9f3253f31d4e17` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
