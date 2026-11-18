# Audit report `aud-fault-silent-crm-edit`

**Outcome: DISCREPANCIES**

- Call: `call-fault-silent-crm-edit` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 2, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 1 | Claim trust score: 100% | Highest severity: `HIGH`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Tue Mar 3 2026, 2:30 PM EST exists exactly as claimed (apt_0001).
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I've sent a confirmation text to the number on file."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550109999) | yes |
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

### 2. ConfirmationSent (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Confirmation was sent to +15550101001 as claimed (msg_0001).
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I've sent a confirmation text to the number on file."

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
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The messages change history for the call window was fully observed.

Evidence:
- `messages` `msg_0001`: Message logged during the call (journal #8; net: created)

## Findings beyond claims

### F1. UNCLAIMED_WRITE: `unclaimed_patient_modified`

- **Severity:** `HIGH`
- **Finding:** The agent edited a patient record without saying so. (pat_0001)
- **Fix:** Review the write with the patient or revert it.
- Evidence `crm` `pat_0001`: Write by the agent that no claim accounts for (journal #7; net: updated)

## Audit trail

1. `evidence` calendar: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-silent-crm-edit-c1 (AppointmentBooked): exact match -> apt_0001
7. `reconcile` call-fault-silent-crm-edit-c2 (ConfirmationSent): exact match -> msg_0001
8. `verdict` call-fault-silent-crm-edit-c1 (AppointmentBooked): VERIFIED
9. `verdict` call-fault-silent-crm-edit-c2 (ConfirmationSent): VERIFIED
10. `reconcile` pat_0001: updated by the agent, no claim covers it
11. `verdict` Outcome: DISCREPANCIES

## Seal

- content `f5b080dc6c980261cc3e8780f44c6335e80883e55cbf86deecc5c71ee6ff9338`
- chain `0a930031d2059801d0239259067bcfc1026f81d1676e57e5ef6b14546db30d97` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
