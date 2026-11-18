# Audit report `aud-clean-inquiry-only`

**Outcome: CLEAN**

- Call: `call-clean-inquiry-only` | Agent: `agent:receptionist` | Caller: Maya Chen
- Window: 2026-03-02T09:05:00-05:00 to 2026-03-02T09:05:16-05:00
- Claims: 0 | verified 0, mismatch 0, not found 0, unverifiable 0
- Findings beyond claims: 0 | Claim trust score: n/a | Highest severity: `INFO`
- Audited by `subpoena/0.1.0` at 2026-03-02T09:06:16-05:00
- Extraction: `rules`
- Provenance (platform-supplied, unverified): agent `receptionist-sim/0.1.0` | prompt `narrator:standard` | human handoffs: 0

## Claims

The agent made no claims in this call.

## Findings beyond claims

None. Every write the agent made is accounted for by a claim.

## Audit trail

1. `evidence` calendar: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
2. `evidence` crm: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
3. `evidence` messages: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
4. `evidence` tickets: 0 write(s) stamped to this call, 0 under the shared agent identity in the call window
5. `claims` 0 structured claim(s); 0 recovered from the transcript, 0 of them never logged by the agent
6. `verdict` Outcome: CLEAN

## Seal

- content `4f5c2aa5ce8c0d35b1bb6ac990392ff86d22de361c290dbca36c053e0fdd1113`
- chain `9586a1fcb3ffbcebce782b0b05b731685bb74e8bba480f2a6de679f4e32352a9` (prev `0000000000000000...`)
- signed (key `6508b98a7ace`)
