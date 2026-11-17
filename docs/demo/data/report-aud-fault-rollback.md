# Audit report `aud-fault-rollback`

**Outcome: DISCREPANCIES**

- Call: `call-fault-rollback` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 1, mismatch 0, not found 1, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 50% | Highest severity: `CRITICAL`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

## Claims

### 1. AppointmentBooked (logged claim): NO RECEIPT

- **Status:** `NOT_FOUND` | **Severity:** `CRITICAL`
- **Finding:** The agent claimed it booked Maya Chen on Tue Mar 3 2026, 2:30 PM EST. An appointment was written and then removed during the call, so nothing is on the books.
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I just texted you a confirmation."
- **Fix:** Create the appointment or call the patient back before they show up.

Checks:
- `existence`: FAIL. No write by the agent during the call corresponds to this claim.
- `exactness`: n/a. Nothing to compare.
- `side_effects`: n/a. Nothing to compare.

Evidence:
- `journal` `calendar 2026-03-02T09:05:00-05:00 .. 2026-03-02T09:05:46-05:00`: 2 agent write(s) to calendar in the call window. None creates this booking.
- `calendar` `apt_0001`: Written, then removed, within the same call (journal #6, #7; net: transient)

### 2. ConfirmationSent (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Confirmation was sent to +15550101001 as claimed (msg_0001).
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I just texted you a confirmation."

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

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 2 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 1 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-rollback-c2 (ConfirmationSent): exact match -> msg_0001
7. `reconcile` call-fault-rollback-c1 (AppointmentBooked): no write corresponds
8. `verdict` call-fault-rollback-c1 (AppointmentBooked): NOT_FOUND
9. `verdict` call-fault-rollback-c2 (ConfirmationSent): VERIFIED
10. `verdict` Outcome: DISCREPANCIES

## Seal

- content `887d9c9c27431c7facb25d18e0467afb53c40dcd0c48d61532a35ac69c349e37`
- chain `a1352fb6eab49ea435a1b565a90ab895007b6c82e334cacfc2654e02b9e4ec79` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
