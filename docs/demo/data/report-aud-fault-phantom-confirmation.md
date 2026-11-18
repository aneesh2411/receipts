# Audit report `aud-fault-phantom-confirmation`

**Outcome: DISCREPANCIES**

- Call: `call-fault-phantom-confirmation` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 1, mismatch 0, not found 1, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 50% | Highest severity: `MEDIUM`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Tue Mar 3 2026, 2:30 PM EST exists exactly as claimed (apt_0001).
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I've sent a confirmation text to the number on file."

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

### 2. ConfirmationSent (logged claim): NO RECEIPT

- **Status:** `NOT_FOUND` | **Severity:** `MEDIUM`
- **Finding:** The agent claimed it sent an SMS confirmation to +15550101001, but the message log shows nothing sent during the call.
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I've sent a confirmation text to the number on file."
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

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-phantom-confirmation-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-fault-phantom-confirmation-c2 (ConfirmationSent): no write corresponds
8. `verdict` call-fault-phantom-confirmation-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-fault-phantom-confirmation-c2 (ConfirmationSent): NOT_FOUND
10. `verdict` Outcome: DISCREPANCIES

## Seal

- content `f97f4038e0ccf9f2e017842b9eaa8a099567700056fe74dacddcc47f04741dfa`
- chain `9354dae9e787bc3c6a1994499d2fdf15a8a0f31823ae060ec37e555bfdcde46d` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
