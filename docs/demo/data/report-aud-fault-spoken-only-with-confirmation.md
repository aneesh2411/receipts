# Audit report `aud-fault-spoken-only-with-confirmation`

**Outcome: DISCREPANCIES**

- Call: `call-fault-spoken-only-with-confirmation` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 0, mismatch 0, not found 2, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `CRITICAL`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

## Claims

### 1. AppointmentBooked (said to caller, never logged): NO RECEIPT

- **Status:** `NOT_FOUND` | **Severity:** `CRITICAL`
- **Finding:** The agent claimed it booked Maya Chen on Tue Mar 3 2026, 2:30 PM EST, but no appointment was created during the call.
- **What the caller heard (turn 2):** "I scheduled your cleaning with Dr. Patel for Tuesday, March 3 at 2:30 PM."
- **Fix:** Create the appointment or call the patient back before they show up.

Checks:
- `existence`: FAIL. No write by the agent during the call corresponds to this claim.
- `exactness`: n/a. Nothing to compare.
- `side_effects`: n/a. Nothing to compare.

Evidence:
- `journal` `calendar 2026-03-02T09:05:00-05:00 .. 2026-03-02T09:05:46-05:00`: 0 agent write(s) to calendar in the call window. None creates this booking.

### 2. ConfirmationSent (said to caller, never logged): NO RECEIPT

- **Status:** `NOT_FOUND` | **Severity:** `MEDIUM`
- **Finding:** The agent claimed it sent an SMS confirmation to +15550101001, but the message log shows nothing sent during the call.
- **What the caller heard (turn 2):** "I've sent a confirmation text to the number on file."
- **Fix:** Send the confirmation the caller was promised.

Checks:
- `existence`: FAIL. No write by the agent during the call corresponds to this claim.
- `exactness`: n/a. Nothing to compare.
- `side_effects`: n/a. Nothing to compare.

Evidence:
- `journal` `messages 2026-03-02T09:05:00-05:00 .. 2026-03-02T09:05:46-05:00`: 0 agent write(s) to messages in the call window. None is this confirmation.

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 0 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 0 structured claim(s); 2 recovered from the transcript, 2 of them never logged by the agent
6. `reconcile` call-fault-spoken-only-with-confirmation-t1 (AppointmentBooked): no write corresponds
7. `reconcile` call-fault-spoken-only-with-confirmation-t2 (ConfirmationSent): no write corresponds
8. `verdict` call-fault-spoken-only-with-confirmation-t1 (AppointmentBooked): NOT_FOUND
9. `verdict` call-fault-spoken-only-with-confirmation-t2 (ConfirmationSent): NOT_FOUND
10. `verdict` Outcome: DISCREPANCIES

## Seal

- content `88c2d1a616273fdaaa598b818ddb2cbeb0a4c16040efb466d1d390a86e7b4ced`
- chain `cf624027fcf36d1b256e72fa276dcec370b33f952a994f048858c57fa5772e41` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
