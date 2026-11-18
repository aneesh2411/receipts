# Audit report `aud-clean-inquiry-only`

**Outcome: CLEAN**

- Call: `call-clean-inquiry-only` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 0 | verified 0, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: n/a | Highest severity: `INFO`
- Audited by `receipts/0.1.0` at 2026-03-02T09:06:16-05:00
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

The agent made no claims in this call.

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 0 journal row(s) by agent:receptionist in the call window
2. `evidence` crm: 0 journal row(s) by agent:receptionist in the call window
3. `evidence` messages: 0 journal row(s) by agent:receptionist in the call window
4. `evidence` tickets: 0 journal row(s) by agent:receptionist in the call window
5. `claims` 0 structured claim(s); 0 recovered from the transcript, 0 of them never logged by the agent
6. `verdict` Outcome: CLEAN

## Seal

- content `8319ec04947161ec1b694544f289a5c7579294e84e94801b85f684bb656fa718`
- chain `bc933e9a02722e471e30a5c0286d919fc224ab0258cd3d882c0338d5b8869814` (prev `0000000000000000...`)
- signed (key `952a7ab34a0a`)
