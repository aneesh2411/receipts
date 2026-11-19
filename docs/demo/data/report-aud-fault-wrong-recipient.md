# Audit report `aud-fault-wrong-recipient`

**Outcome: DISCREPANCIES**

- Call: `call-fault-wrong-recipient` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 1, mismatch 1, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 50% | Highest severity: `HIGH`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Extraction: `rules`
- Seal: sha256 chain `dcc4616019055a5df8f70aba...`, signed (key `6508b98a7ace`)
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Tue Mar 3 2026, 2:30 PM EST exists exactly as claimed (apt_0001).
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Patel on Tuesday, March 3 at 2:30 PM. I just texted you a confirmation."

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
- `calendar` `apt_0001`: Appointment written by the agent during the call (journal #6; net: created)

### 2. ConfirmationSent (logged claim): RECEIPT DOES NOT MATCH

- **Status:** `MISMATCH` | **Severity:** `HIGH`
- **Finding:** A message was sent (msg_0001) but it is not the confirmation claimed. recipient: claimed +15550101001, actual +15550101010.
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Patel on Tuesday, March 3 at 2:30 PM. I just texted you a confirmation."
- **Fix:** Send a corrected confirmation to the right recipient. If it went to a stranger, treat it as a privacy incident.

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| recipient | +15550101001 | +15550101010 | **NO** |
| channel | sms | sms | yes |
| delivery | sent | sent | yes |
| stated_time | Tue Mar 3 2026, 2:30 PM EST | Tue Mar 3 2026, 2:30 PM EST | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: FAIL. Differs on: recipient.
- `side_effects`: n/a. Not applicable.
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The messages change history for the call window was fully observed.

Evidence:
- `messages` `msg_0001`: Message logged during the call (journal #7; net: created)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-wrong-recipient-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-fault-wrong-recipient-c2 (ConfirmationSent): partial match -> msg_0001
8. `verdict` call-fault-wrong-recipient-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-fault-wrong-recipient-c2 (ConfirmationSent): MISMATCH
10. `verdict` Outcome: DISCREPANCIES

## Seal

- content `42a4189b13d6dfcf5ce3c17346e9684cabc85df8a9a6cf439b45f925ec194d87`
- chain `dcc4616019055a5df8f70abad881819b86bd2e85101af176d32810b287222fd5` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
