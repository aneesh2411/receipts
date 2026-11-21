# Audit report `aud-correction-honored`

**Outcome: CLEAN**

- Call: `call-correction-honored` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:24-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:24-05:00
- Extraction: `rules`
- Seal: sha256 chain `9f0472d6fbc74cf97836e000...`, signed (key `6508b98a7ace`)
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Booking for Maya Chen on Wed Mar 4 2026, 2:30 PM EST exists exactly as claimed (apt_0001).
- **What the caller heard (turn 4):** "No problem at all. I've booked you for Wednesday, March 4 at 2:30 PM instead."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| patient | Maya Chen (+15550101001) | Maya Chen (+15550101001) | yes |
| start | Wed Mar 4 2026, 2:30 PM EST | Wed Mar 4 2026, 2:30 PM EST | yes |
| provider | Dr. Patel | Dr. Patel | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.
- `attribution`: pass. Every backing write carries this call's own stamp.
- `coverage`: pass. The calendar change history for the call window was fully observed.

Evidence:
- `calendar` `apt_0001`: Appointment written by the agent during the call (journal #6, #7; net: created)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 2 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 2 structured claim(s); 2 recovered from the transcript, 0 of them never logged by the agent
6. `claims` call-correction-honored-c2 corrects call-correction-honored-c1 (turn 4); the earlier AppointmentBooked claim is withdrawn, the corrected value is what the caller is owed
7. `reconcile` call-correction-honored-c2 (AppointmentBooked): exact match -> apt_0001
8. `verdict` call-correction-honored-c2 (AppointmentBooked): VERIFIED
9. `verdict` Outcome: CLEAN

## Seal

- content `1b5b49bb97dbbdcab0e6caba7d6cb09a8c1d2baccea1e718daf29cd7e974772e`
- chain `9f0472d6fbc74cf97836e00061bc61dbba9a8709a6dd20be306bb294d8e30e46` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
