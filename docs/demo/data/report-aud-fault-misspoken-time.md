# Audit report `aud-fault-misspoken-time`

**Outcome: DISCREPANCIES**

- Call: `call-fault-misspoken-time` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 3 | verified 2, mismatch 0, not found 1, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 67% | Highest severity: `CRITICAL`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Tue Mar 3 2026, 2:30 PM EST exists exactly as claimed (apt_0001).
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Wednesday, March 4 at 2:30 PM. I just texted you a confirmation."

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
- `calendar` `apt_0001`: Appointment written by the agent during the call (journal #6; net: created)

### 2. ConfirmationSent (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Confirmation was sent to +15550101001 as claimed (msg_0001).
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Wednesday, March 4 at 2:30 PM. I just texted you a confirmation."

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
- `messages` `msg_0001`: Message logged during the call (journal #7; net: created)

### 3. AppointmentBooked (said to caller, never logged): NO RECEIPT

- **Status:** `NOT_FOUND` | **Severity:** `CRITICAL`
- **Finding:** The agent claimed it booked Maya Chen on Wed Mar 4 2026, 2:30 PM EST, but no appointment was created during the call.
- **What the caller heard (turn 2):** "I've booked your cleaning with Dr. Patel on Wednesday, March 4 at 2:30 PM."
- **Fix:** Create the appointment or call the patient back before they show up.

Checks:
- `existence`: FAIL. No write by the agent during the call corresponds to this claim.
- `exactness`: n/a. Nothing to compare.
- `side_effects`: n/a. Nothing to compare.

Evidence:
- `journal` `calendar 2026-03-02T09:05:00-05:00 .. 2026-03-02T09:05:46-05:00`: 1 agent write(s) to calendar in the call window. None creates this booking.

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 1 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 1 of them never logged by the agent
6. `reconcile` call-fault-misspoken-time-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-fault-misspoken-time-c2 (ConfirmationSent): exact match -> msg_0001
8. `reconcile` call-fault-misspoken-time-t1 (AppointmentBooked): no write corresponds
9. `verdict` call-fault-misspoken-time-c1 (AppointmentBooked): VERIFIED
10. `verdict` call-fault-misspoken-time-c2 (ConfirmationSent): VERIFIED
11. `verdict` call-fault-misspoken-time-t1 (AppointmentBooked): NOT_FOUND
12. `verdict` Outcome: DISCREPANCIES

## Seal

- content `e1809efe5f71abc425d6decdf0e5da47cd7b70df1a8315f13b999f3e494d2a41`
- chain `a549a96b15669b59ace363b3954f66707c85f144369bd08dbfe8c0196dd6ecad` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
