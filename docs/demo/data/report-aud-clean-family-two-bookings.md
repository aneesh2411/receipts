# Audit report `aud-clean-family-two-bookings`

**Outcome: CLEAN**

- Call: `call-clean-family-two-bookings` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:24-05:00
- Claims: 3 | verified 3, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:24-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Wed Mar 4 2026, 9:00 AM EST exists exactly as claimed (apt_0001).
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Kim on Wednesday, March 4 at 9:00 AM. I've sent a confirmation text to the number on file."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550101001) | yes |
| start | Wed Mar 4 2026, 9:00 AM EST | Wed Mar 4 2026, 9:00 AM EST | yes |
| provider | Dr. Kim | Dr. Kim | yes |
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
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Kim on Wednesday, March 4 at 9:00 AM. I've sent a confirmation text to the number on file."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| recipient | +15550101001 | +15550101001 | yes |
| channel | sms | sms | yes |
| delivery | sent | sent | yes |
| stated_time | Wed Mar 4 2026, 9:00 AM EST | Wed Mar 4 2026, 9:00 AM EST | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.

Evidence:
- `messages` `msg_0001`: Message logged during the call (journal #7; net: created)

### 3. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Sofia Alvarez on Wed Mar 4 2026, 9:30 AM EST exists exactly as claimed (apt_0002).
- **What the caller heard (turn 4):** "Done. I scheduled your cleaning with Dr. Kim for Wednesday, March 4 at 9:30 AM."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Sofia Alvarez (+15550101005) | Sofia Alvarez (+15550101005) | yes |
| start | Wed Mar 4 2026, 9:30 AM EST | Wed Mar 4 2026, 9:30 AM EST | yes |
| provider | Dr. Kim | Dr. Kim | yes |
| duration | 30 min | 30 min | yes |
| reason | cleaning | cleaning | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.

Evidence:
- `calendar` `apt_0002`: Appointment written by the agent during the call (journal #8; net: created)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 2 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 1 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 3 structured claim(s); 3 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-clean-family-two-bookings-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-clean-family-two-bookings-c3 (AppointmentBooked): exact match -> apt_0002
8. `reconcile` call-clean-family-two-bookings-c2 (ConfirmationSent): exact match -> msg_0001
9. `verdict` call-clean-family-two-bookings-c1 (AppointmentBooked): VERIFIED
10. `verdict` call-clean-family-two-bookings-c2 (ConfirmationSent): VERIFIED
11. `verdict` call-clean-family-two-bookings-c3 (AppointmentBooked): VERIFIED
12. `verdict` Outcome: CLEAN

## Seal

- content `fad1b5c161751c2d10604c198e0f1d7daa30f4f0818f5c362f94028daa3cb042`
- chain `07a5206a6218bec5ab0642df4add26eb7a627f02c07e2d3601fe099a8ac308d0` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
