# Audit report `aud-fault-reschedule-rewrite`

**Outcome: DISCREPANCIES**

- Call: `call-fault-reschedule-rewrite` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 0, mismatch 1, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 0% | Highest severity: `MEDIUM`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00

## Claims

### 1. Rescheduled (logged claim): RECEIPT DOES NOT MATCH

- **Status:** `MISMATCH` | **Severity:** `MEDIUM`
- **Finding:** The calendar changed, but not the way the caller was told. rewrite_provider: claimed unchanged, actual now Dr. Kim; rewrite_duration: claimed unchanged, actual now 60 min; provider: claimed Dr. Patel, actual Dr. Kim.
- **What the caller heard (turn 2):** "All done. Your visit is rescheduled from Tuesday, March 3 at 10:00 AM to Thursday, March 5 at 11:00 AM."
- **Fix:** Reconcile the calendar with what the caller was told: one appointment, at the promised time, and the old slot released.

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| new_start | Thu Mar 5 2026, 11:00 AM EST | Thu Mar 5 2026, 11:00 AM EST | yes |
| old_start | Tue Mar 3 2026, 10:00 AM EST | Tue Mar 3 2026, 10:00 AM EST | yes |
| old_slot_released | released | released (same record moved) | yes |
| rewrite_provider | unchanged | now Dr. Kim | **NO** |
| rewrite_duration | unchanged | now 60 min | **NO** |
| provider | Dr. Patel | Dr. Kim | **NO** |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: FAIL. Differs on: provider.
- `side_effects`: FAIL. Failed: rewrite_provider, rewrite_duration.

Evidence:
- `calendar` `apt_0001`: Changed by the agent during the call (journal #7, #8; net: updated)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 2 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-fault-reschedule-rewrite-c1 (Rescheduled): exact match -> apt_0001
7. `verdict` call-fault-reschedule-rewrite-c1 (Rescheduled): MISMATCH
8. `verdict` Outcome: DISCREPANCIES

## Seal

- content `b83718612484d9650c92c399e3096e9748e32b4ec566fde8e62da08c614128c9`
- chain `17ee5cd9b2d25a33f443c9b9608cccb28af9f31942f06a802e9db415230bfc7d` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
