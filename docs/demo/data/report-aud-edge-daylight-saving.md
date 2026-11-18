# Audit report `aud-edge-daylight-saving`

**Outcome: CLEAN**

- Call: `call-edge-daylight-saving` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 2, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Mon Mar 9 2026, 9:00 AM EDT exists exactly as claimed (apt_0001).
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Patel on Monday, March 9 at 9:00 AM. I've sent a confirmation text to the number on file."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550101001) | yes |
| start | Mon Mar 9 2026, 9:00 AM EDT | Mon Mar 9 2026, 9:00 AM EDT | yes |
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
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Patel on Monday, March 9 at 9:00 AM. I've sent a confirmation text to the number on file."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| recipient | +15550101001 | +15550101001 | yes |
| channel | sms | sms | yes |
| delivery | sent | sent | yes |
| stated_time | Mon Mar 9 2026, 9:00 AM EDT | Mon Mar 9 2026, 9:00 AM EDT | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
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
6. `reconcile` call-edge-daylight-saving-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-edge-daylight-saving-c2 (ConfirmationSent): exact match -> msg_0001
8. `verdict` call-edge-daylight-saving-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-edge-daylight-saving-c2 (ConfirmationSent): VERIFIED
10. `verdict` Outcome: CLEAN

## Seal

- content `16c7463eb88a35754cb339b29b9238cfb7d55c01771bf66fbde1af39dd82b257`
- chain `ccf0ef4a57826154e0447d512a4dca1133d964c6c9fb0ba3304155520e40b2b3` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
