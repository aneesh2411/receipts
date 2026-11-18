# Audit report `aud-fault-reschedule-wrong-time`

**Outcome: DISCREPANCIES**

- Call: `call-fault-reschedule-wrong-time` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 1, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `CRITICAL`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. Rescheduled (logged claim): RECEIPT DOES NOT MATCH

- **Status:** `MISMATCH` | **Severity:** `CRITICAL`
- **Finding:** The calendar changed, but not the way the caller was told. new_start: claimed Thu Mar 5 2026, 11:00 AM EST, actual Thu Mar 5 2026, 12:00 PM EST.
- **What the caller heard (turn 2):** "All done. Your visit is rescheduled from Tuesday, March 3 at 10:00 AM to Thursday, March 5 at 11:00 AM."
- **Fix:** Reconcile the calendar with what the caller was told: one appointment, at the promised time, and the old slot released.

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| new_start | Thu Mar 5 2026, 11:00 AM EST | Thu Mar 5 2026, 12:00 PM EST | **NO** |
| old_start | Tue Mar 3 2026, 10:00 AM EST | Tue Mar 3 2026, 10:00 AM EST | yes |
| old_slot_released | released | released (same record moved) | yes |
| provider | Dr. Patel | Dr. Patel | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: FAIL. Differs on: new_start.
- `side_effects`: pass. Side effects are as claimed.

Evidence:
- `calendar` `apt_0001`: Changed by the agent during the call (journal #7; net: updated)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-reschedule-wrong-time-c1 (Rescheduled): partial match -> apt_0001
7. `verdict` call-fault-reschedule-wrong-time-c1 (Rescheduled): MISMATCH
8. `verdict` Outcome: DISCREPANCIES

## Seal

- content `93977c1c983a92520276ab4fc4775f507a3b5621565df8721d20f16d1dcae16a`
- chain `6053e967e0d4135563afae5fe4b9bfc1e7a261d01f6a7f2b9e6cded622763160` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
