# Subpoena FAQ

## What does each verdict mean?

A verdict answers one claim, such as “I booked your appointment for 2:30.”
The status comes from `VerdictStatus` in [`models.py`](../src/subpoena/models.py).
Here is how to read it for a booking claim.

| Status | What it means |
| --- | --- |
| `VERIFIED` | The calendar shows a write attributable to the agent in the audit window, and the details checked match the claim. The appointment was booked for 2:30 as promised. |
| `MISMATCH` | The auditor found a corresponding write, but a checked detail differs. For example, the calendar shows 3:30 when the agent said 2:30. |
| `NOT_FOUND` | The auditor could check the relevant history and found no corresponding write for the claim in the audit window. A booking that was already on the calendar does not establish that the agent booked it on this call. |
| `UNVERIFIABLE` | The auditor could not check the claim reliably. The calendar could be down, its history could be incomplete, or the patient or writing call could be ambiguous. The auditor leaves the claim undecided. |

The report includes the available evidence and any differences between the
claimed and recorded details. The shared verdict builders live in
[`auditor/verdicts.py`](../src/subpoena/auditor/verdicts.py).

## Where will I see INCONCLUSIVE?

The call report has an overall `Outcome`. The auditor returns
`DISCREPANCIES` if it finds a mismatch, a missing write for a claim, or a
finding such as a double booking. Otherwise it returns `INCONCLUSIVE` if a
claim is unverifiable or a system's change history is unreadable or incomplete.
That gap can hide writes even when the call made no claims about that system.
The remaining outcome is `CLEAN`. See `_outcome` in
[`auditor/engine.py`](../src/subpoena/auditor/engine.py).

A follow-up check after a repair also has a `Resolution` status. Its
`INCONCLUSIVE` member is reported as `inconclusive` when the latest
snapshot cannot be read or evaluated. The check stays `pending` while it has
yet to establish a fix. It reaches `verified_closed` when the two latest
snapshots both match the original claim and are far enough apart. See
`decide` in [`auditor/resolution.py`](../src/subpoena/auditor/resolution.py).

## Why doesn't a model decide the verdict?

What the agent says on the call or logs in a tool event gives the auditor a
claim to check. `Auditor` reads the history of changes from your system of
record, such as your calendar, CRM, message log or ticket queue. It uses the
call's time window and write attribution to match claims to recorded changes,
then compares the relevant fields using fixed rules. Given the same claims
and evidence, those rules produce the same verdict. See the
[architecture](ARCHITECTURE.md) and [auditor engine](../src/subpoena/auditor/engine.py).

An optional model can help extract claims from the transcript. The default
extractor uses rules and runs offline. Either extractor supplies claims for
the same evidence checks. A model can affect which spoken claims are picked
up, and the quality of your records and attribution limits what the auditor
can verify.

## Known limits

Audit windows have a one-second resolution because the system of record stores
write timestamps at second precision. A write in the same second as either
audit-window boundary is treated as inside the window. The future option for
microsecond precision is tracked in [issue #116](https://github.com/aneesh2411/subpoena/issues/116).

## What does the demo prove?

The demo uses simulated calls and records so you can see how the audit
behaves. Its public signing key lets you try seal verification on those demo
reports. Anyone with that key can sign a report, so a valid demo signature
cannot establish who produced it. To audit your own calls, supply their
records and readers for your systems of record. See the
[integration examples](INTEGRATIONS.md) and the [reader guide](EXTENDING.md).
