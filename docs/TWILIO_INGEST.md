# Offline Twilio Voice ingest

Pass three local files for the same call leg. The first two files are JSON
objects exported from separate Twilio form callbacks. The third is a saved
single-call REST response.

| File | Required fields |
| --- | --- |
| Completed Voice status callback | `CallSid`, `CallStatus=completed`, `From`, `To`, `Timestamp` |
| Completed TwiML `<Record>` transcription callback | `CallSid`, `TranscriptionStatus=completed`, `From`, `To`, `TranscriptionText` |
| REST Call resource | `sid`, `status=completed`, `from`, `to`, `start_time`, `end_time` |

Call IDs and signaling addresses must match exactly across the files. The Call
resource uses native REST keys and UTC RFC 2822 timestamps. Its start and end
supply the ordered audit window. The callback event timestamp is recorded
separately in provenance and must be at or after the Call resource's end.
[Twilio Call resource and status callbacks](https://www.twilio.com/docs/voice/api/call-resource) ·
[Twilio Record transcription callback](https://www.twilio.com/docs/voice/twiml/record#transcribecallback)

Run this example from the checkout root with the project's CLI installed.

```sh
subpoena ingest-twilio \
  tests/fixtures/twilio/completed-status.json \
  tests/fixtures/twilio/completed-transcription.json \
  tests/fixtures/twilio/completed-call-resource.json \
  --agent-id test-agent --agent-version v3 --caller-name "Test Caller"
```

The command emits `CallRecord` JSON to stdout. Use `--out /tmp/call-record.json`
to write it to a file. The three operator flags are required. Set the agent ID to
the deployment's system-of-record audit actor ID and supply the caller name
from your deployment records. The model's `caller.phone` stores the exact Twilio
`From` signaling address, which can be a client identifier and does not establish
a person's identity.

The plain transcription is preserved in `raw_transcript`. The timed
`transcript` stays empty. The existing auditor can reconcile system-of-record
writes with structured claims, while its transcript extractor has zero turns
to read.

## Optional deployment claims

Add `--claims tests/fixtures/twilio/structured-claims.json` to load Subpoena's
per-call deployment export. This format comes from the deployment's tool-call
log and has a top-level `call_id` and a `claims` array. Each claim uses the
existing typed Subpoena claim schema. Retain the log's `claim_id` and
`turn_index`. The index is a log reference here, with no corresponding timed
transcript turn. Omit `source` to use the model's `structured` default, or set
it explicitly to `structured`. Claim contents remain assertions until the
auditor checks them against independent system-of-record evidence. Without
the export, the ingest produces zero claims.

The files are operator-supplied and the CLI checks their internal consistency.
A capture system that requires verified origin must authenticate the original
webhook before export. The CLI operates offline and has no Twilio credentials.
[Twilio webhook security](https://www.twilio.com/docs/usage/webhooks/webhooks-security)

The offline test `test_existing_auditor_consumes_cli_json` runs the CLI with
and without the claim export, parses its JSON, and audits against a local SQLite
store. The claim variant is verified by an independent synthetic SMS journal
entry.

## The demo story

`docs/demo/twilio/` ships a second, realistic fixture set: an inbound call to
the demo clinic whose agent claims a Tuesday 3 PM booking and a confirmation
text. `scripts/export_demo.py` ingests those files, audits them against a
record that holds the text but no appointment, and bakes the result into the
GitHub Pages demo under "Arrived via Twilio ingest".
