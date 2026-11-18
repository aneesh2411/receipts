# Audit report `aud-fault-cancel-wrong-appointment`

**Outcome: DISCREPANCIES**

- Call: `call-fault-cancel-wrong-appointment` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 1, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `CRITICAL`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. Cancelled (logged claim): RECEIPT DOES NOT MATCH

- **Status:** `MISMATCH` | **Severity:** `CRITICAL`
- **Finding:** The agent cancelled a different appointment (apt_0002) than it claimed. start: claimed Tue Mar 3 2026, 10:00 AM EST, actual Tue Mar 10 2026, 3:00 PM EDT.
- **What the caller heard (turn 2):** "I've cancelled your appointment on Tuesday, March 3 at 10:00 AM."
- **Fix:** Restore the wrongly cancelled appointment and cancel the intended one.

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| start | Tue Mar 3 2026, 10:00 AM EST | Tue Mar 10 2026, 3:00 PM EDT | **NO** |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: FAIL. Differs on: start.
- `side_effects`: n/a. Not applicable.
- `attribution`: pass. Every backing write carries this call's own stamp.

Evidence:
- `calendar` `apt_0002`: Released by the agent during the call (journal #8; net: updated)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-cancel-wrong-appointment-c1 (Cancelled): partial match -> apt_0002
7. `verdict` call-fault-cancel-wrong-appointment-c1 (Cancelled): MISMATCH
8. `verdict` Outcome: DISCREPANCIES

## Seal

- content `49de8749b6aeab0b74293672fe7725825f7050879e3a64b407504c8e53383642`
- chain `77946a68e8aab49c1ee1468fae039261885a731fe4030ffc3901afed44c40daa` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
