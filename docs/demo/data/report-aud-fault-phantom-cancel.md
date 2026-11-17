# Audit report `aud-fault-phantom-cancel`

**Outcome: DISCREPANCIES**

- Call: `call-fault-phantom-cancel` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 0, not found 1, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `MEDIUM`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

## Claims

### 1. Cancelled (logged claim): NO RECEIPT

- **Status:** `NOT_FOUND` | **Severity:** `MEDIUM`
- **Finding:** The agent claimed it cancelled the appointment for Maya Chen on Tue Mar 3 2026, 10:00 AM EST, but it is still on the books (apt_0001).
- **What the caller heard (turn 2):** "Your appointment on Tuesday, March 3 at 10:00 AM is now cancelled."
- **Fix:** Cancel the appointment so the slot is released and the patient is not charged for a no-show.

Checks:
- `existence`: FAIL. No write by the agent during the call corresponds to this claim.
- `exactness`: n/a. Nothing to compare.
- `side_effects`: n/a. Nothing to compare.

Evidence:
- `journal` `calendar 2026-03-02T09:05:00-05:00 .. 2026-03-02T09:05:46-05:00`: 0 agent write(s) to calendar in the call window. None cancels this appointment.
- `calendar` `apt_0001`: Still booked (current state)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 0 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-phantom-cancel-c1 (Cancelled): no write corresponds
7. `verdict` call-fault-phantom-cancel-c1 (Cancelled): NOT_FOUND
8. `verdict` Outcome: DISCREPANCIES

## Seal

- content `e1fc212fae28d761550bac6bffd1b64721c3ca96672440457f060ba197a33448`
- chain `90ada4aaa2d79f487a4c0f67b28d0141e1240be215847047f520a1d36e1a73fb` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
