# Audit report `aud-edge-preexisting-match`

**Outcome: DISCREPANCIES**

- Call: `call-edge-preexisting-match` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 0, not found 1, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `LOW`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

## Claims

### 1. AppointmentBooked (logged claim): NO RECEIPT

- **Status:** `NOT_FOUND` | **Severity:** `LOW`
- **Finding:** The agent claimed it booked Maya Chen on Tue Mar 3 2026, 2:30 PM EST, but wrote nothing during this call. An identical appointment (apt_0001) already existed: the caller's outcome holds, the claim does not.
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM."
- **Fix:** No patient impact. Flag the agent for taking credit for a write it did not make.

Checks:
- `existence`: FAIL. No write by the agent during the call corresponds to this claim.
- `exactness`: n/a. Nothing to compare.
- `side_effects`: n/a. Nothing to compare.

Evidence:
- `journal` `calendar 2026-03-02T09:05:00-05:00 .. 2026-03-02T09:05:46-05:00`: 0 agent write(s) to calendar in the call window. None creates this booking.
- `calendar` `apt_0001`: Already on the books before this call started (current state)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 0 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-edge-preexisting-match-c1 (AppointmentBooked): no write corresponds
7. `verdict` call-edge-preexisting-match-c1 (AppointmentBooked): NOT_FOUND
8. `verdict` Outcome: DISCREPANCIES

## Seal

- content `ca3d9baae2ee850c7279f45cc89a89c68b1a20357b07c3dbef4c3fe072616f59`
- chain `3352030fa1538b45771ba7fc955fbeb3d39034f274f803098db305d62c218e44` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
