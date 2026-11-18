# Audit report `aud-clean-book-new-patient`

**Outcome: CLEAN**

- Call: `call-clean-book-new-patient` | Agent: `agent:receptionist` | Caller: Leo Martins
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 2, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Leo Martins on Wed Mar 4 2026, 10:00 AM EST exists exactly as claimed (apt_0001).
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Kim on Wednesday, March 4 at 10:00 AM. I've sent a confirmation text to the number on file."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Leo Martins (+15550101099) | Leo Martins (+15550101099) | yes |
| start | Wed Mar 4 2026, 10:00 AM EST | Wed Mar 4 2026, 10:00 AM EST | yes |
| provider | Dr. Kim | Dr. Kim | yes |
| duration | 30 min | 30 min | yes |
| reason | cleaning | cleaning | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.

Evidence:
- `calendar` `apt_0001`: Appointment written by the agent during the call (journal #7; net: created)

### 2. ConfirmationSent (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Confirmation was sent to +15550101099 as claimed (msg_0001).
- **What the caller heard (turn 2):** "Okay, I've got you down with Dr. Kim on Wednesday, March 4 at 10:00 AM. I've sent a confirmation text to the number on file."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| recipient | +15550101099 | +15550101099 | yes |
| channel | sms | sms | yes |
| delivery | sent | sent | yes |
| stated_time | Wed Mar 4 2026, 10:00 AM EST | Wed Mar 4 2026, 10:00 AM EST | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.

Evidence:
- `messages` `msg_0001`: Message logged during the call (journal #8; net: created)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 1 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 1 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-clean-book-new-patient-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-clean-book-new-patient-c2 (ConfirmationSent): exact match -> msg_0001
8. `verdict` call-clean-book-new-patient-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-clean-book-new-patient-c2 (ConfirmationSent): VERIFIED
10. `reconcile` pat_0006: new patient record implied by a claim
11. `verdict` Outcome: CLEAN

## Seal

- content `ce800933fe1a875a3de007f673f01dc8d246a673d7621f6198a1123755a3cec8`
- chain `cbedcf362446c786237b63ef321eb7c4a74bda95e0351591e3cf4ba32d3de65c` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
