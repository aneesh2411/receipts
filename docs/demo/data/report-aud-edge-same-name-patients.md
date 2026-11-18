# Audit report `aud-edge-same-name-patients`

**Outcome: INCONCLUSIVE**

- Call: `call-edge-same-name-patients` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 0, not found 0, unverifiable 1
- Findings beyond claims: 0 | Claim trust score: n/a | Highest severity: `HIGH`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. AppointmentBooked (logged claim): COULD NOT CHECK

- **Status:** `UNVERIFIABLE` | **Severity:** `HIGH`
- **Finding:** Could not be checked: 'Maya Chen' matches 2 patient records and no phone number disambiguates them. A guess here could clear a booking made for the wrong person.
- **What the caller heard (turn 2):** "Done. I scheduled your cleaning with Dr. Patel for Tuesday, March 3 at 2:30 PM."
- **Fix:** Disambiguate the patient (confirm the phone number on file) and re-run the audit.

Checks:
- `existence`: n/a. 'Maya Chen' matches 2 patient records and no phone number disambiguates them

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-edge-same-name-patients-c1 (AppointmentBooked): exact match -> apt_0001
7. `verdict` call-edge-same-name-patients-c1 (AppointmentBooked): UNVERIFIABLE
8. `reconcile` calendar: unclaimed-write check skipped, a claim that may own these writes could not be verified
9. `verdict` Outcome: INCONCLUSIVE

## Seal

- content `535a59bb44bcb120f3c5d2c711be6032469d8d0937bce137ece7db94aaf50b25`
- chain `a6c65afdf4215e68011b38927cf8181e171f7a57668490ebd9cc97a35ab758a9` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
