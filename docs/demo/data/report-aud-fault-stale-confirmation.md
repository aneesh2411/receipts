# Audit report `aud-fault-stale-confirmation`

**Outcome: DISCREPANCIES**

- Call: `call-fault-stale-confirmation` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 1, mismatch 1, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 50% | Highest severity: `HIGH`
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

### 2. ConfirmationSent (logged claim): RECEIPT DOES NOT MATCH

- **Status:** `MISMATCH` | **Severity:** `HIGH`
- **Finding:** A message was sent (msg_0001) but it is not the confirmation claimed. stated_time: claimed Tue Mar 3 2026, 2:30 PM EST, actual Wed Mar 4 2026, 2:30 PM EST.
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I've sent a confirmation text to the number on file."
- **Fix:** Send a corrected confirmation to the right recipient. If it went to a stranger, treat it as a privacy incident.

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| recipient | +15550101001 | +15550101001 | yes |
| channel | sms | sms | yes |
| delivery | sent | sent | yes |
| stated_time | Tue Mar 3 2026, 2:30 PM EST | Wed Mar 4 2026, 2:30 PM EST | **NO** |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: FAIL. Differs on: stated_time.
- `side_effects`: n/a. Not applicable.

Evidence:
- `messages` `msg_0001`: Message logged during the call (journal #7; net: created)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 1 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-stale-confirmation-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-fault-stale-confirmation-c2 (ConfirmationSent): partial match -> msg_0001
8. `verdict` call-fault-stale-confirmation-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-fault-stale-confirmation-c2 (ConfirmationSent): MISMATCH
10. `verdict` Outcome: DISCREPANCIES

## Seal

- content `9ee89db74315b58300de2ef2828bca5f9725dfe456010845e6a922f8df5dce8b`
- chain `ed18b4885c53d641c0a2b2c72b82912e4ea8ffdaee645836ed9b8350c8a2cb88` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
