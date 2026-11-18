# Audit report `aud-clean-cancel`

**Outcome: CLEAN**

- Call: `call-clean-cancel` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 1 | verified 1, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: 100% | Highest severity: `INFO`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

### 1. Cancelled (logged claim): RECEIPT FOUND

- **Status:** `VERIFIED` | **Severity:** `INFO`
- **Finding:** Appointment for Maya Chen on Tue Mar 3 2026, 10:00 AM EST was cancelled as claimed (apt_0001).
- **What the caller heard (turn 2):** "Your appointment on Tuesday, March 3 at 10:00 AM is now cancelled."

| Field | Agent claimed | System of record | Match |
|---|---|---|---|
| start | Tue Mar 3 2026, 10:00 AM EST | Tue Mar 3 2026, 10:00 AM EST | yes |

Checks:
- `existence`: pass. A write by the agent during the call corresponds to this claim.
- `exactness`: pass. All fields match.
- `side_effects`: n/a. Not applicable.

Evidence:
- `calendar` `apt_0001`: Released by the agent during the call (journal #7; net: updated)

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 1 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 1 structured claim(s); 1 recovered from the transcript, 0 of them never logged by the agent
6. `reconcile` call-clean-cancel-c1 (Cancelled): exact match -> apt_0001
7. `verdict` call-clean-cancel-c1 (Cancelled): VERIFIED
8. `verdict` Outcome: CLEAN

## Seal

- content `308f13d7dc6f9179ef58cc36acac94e7672233ed3c47df624e758fad2f051d1b`
- chain `3d2314f63de6bca359d70545ab2d5e57614913e66d1fc6ac1227976d1c0840e0` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
