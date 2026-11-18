# Audit report `aud-edge-message-log-outage`

**Outcome: INCONCLUSIVE**

- Call: `call-edge-message-log-outage` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 2 | verified 1, mismatch 0, not found 0, unverifiable 1
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `MEDIUM`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Extraction: `rules`
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
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The calendar change history for the call window was fully observed.

Evidence:
- `calendar` `apt_0001`: Appointment written by the agent during the call (journal #6; net: created)

### 2. ConfirmationSent (logged claim): COULD NOT CHECK

- **Status:** `UNVERIFIABLE` | **Severity:** `MEDIUM`
- **Finding:** Could not be checked: messages could not be read. No verdict is better than a guessed one.
- **What the caller heard (turn 2):** "You're all set. I've booked your cleaning with Dr. Patel on Tuesday, March 3 at 2:30 PM. I've sent a confirmation text to the number on file."
- **Fix:** Re-run the audit when the system of record is reachable.

Checks:
- `existence`: n/a. messages could not be read

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` messages: UNAVAILABLE (messages adapter is unavailable). Will not guess.
2. `evidence` calendar: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-edge-message-log-outage-c1 (AppointmentBooked): exact match -> apt_0001
7. `verdict` call-edge-message-log-outage-c1 (AppointmentBooked): VERIFIED
8. `verdict` call-edge-message-log-outage-c2 (ConfirmationSent): UNVERIFIABLE
9. `reconcile` messages: unclaimed-write check skipped, a claim that may own these writes could not be verified
10. `verdict` Outcome: INCONCLUSIVE

## Seal

- content `0c1bf86541efb60967c5e3a14ff285e034ed23bb96de551c6144c753eafeca46`
- chain `4120b0a8b4ac0eade086b56d7f8493c017c7594241295495dc0b477af98a89b6` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
