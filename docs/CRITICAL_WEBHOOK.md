# Critical audit webhook

Delivery is disabled by default. Set `SUBPOENA_CRITICAL_WEBHOOK_URL` (or
`Settings.critical_webhook_url`) and a file-backed `SUBPOENA_DB` to enable
it. An unset or empty environment variable disables delivery. An invalid
target or unsupported runtime fails at application startup. Use an installed
Subpoena environment with POSIX interval timers and a trusted HTTPS hostname
on port 443, without URL credentials or a fragment. ASGI lifespan must be
enabled so the server starts the worker.

## Audit persistence and delivery

`POST /audit` and `POST /demo/scenarios/{id}/run` insert each sealed audit
and one outbox row per critical finding or claim verdict in the same SQLite
transaction. If enqueue fails, the transaction rolls back and the request
fails. After a successful commit, the audit and its pending notifications
survive an application restart. The API can return as soon as the audit is
committed, while a background worker delivers independently. Read endpoints,
the standalone CLI demo and offline eval do not deliver alerts.

The JSON contains the event type (`subpoena.critical.v1`), event ID, audit ID,
severity, and JSON Pointers for the result and its evidence entries. Resolve
the pointers against the report object in `data` from the authorized
`GET /audit/{audit_id}/report` response. For example, `/verdicts/0/evidence/0`
identifies the first evidence entry of the first verdict. The payload excludes
transcripts, free text, claim fields, source-system evidence IDs and record
contents.

## Transport

Each attempt has a two-second monotonic deadline covering resolver, TCP,
TLS, write and response headers. The parent supervises a single subprocess
per attempt, kills it at the deadline and reaps it. The child also arms a
POSIX signal watchdog before importing the application, so a child blocked
in DNS can exit even if the worker dies. The deadline includes time spent
launching the child. Process creation and kernel scheduling or reaping
latency are subject to the OS. The response body is not read.

The transport resolves once and rejects empty answers or any nonpublic,
multicast or unsupported address. It connects directly to the first
validated numeric address without a second DNS lookup. TLS checks the chain
and hostname using the system trust store and sends the original hostname
as SNI. HTTP sends the configured host in the Host header. There is no
redirect or proxy handling. The check applies to DNS answers and TCP
addresses. Deployment routing and any transparent intermediaries still
need deployment-level egress controls.

## Attempts, replay and migration

Each app lifespan starts one worker. It polls SQLite at 250 ms intervals and
holds no database write transaction during network I/O. The worker claims
an event in a write transaction with a 30-second lease and a unique token.
It commits a `started` journal entry with the claim. The result and queue
update commit together and must match an unexpired lease token. That check
prevents a stale worker from overwriting a newer attempt. Shutdown stops
polling and joins the worker after its current bounded attempt. A process
crash leaves an expired lease for another worker to recover.

A 2xx response succeeds. HTTP 408, 429, 5xx, connection failures, and deadline
expiry retry. Other HTTP statuses, blocked destinations, certificate
verification failures and unexpected transport errors are terminal. Retry
backoff is one second after the first attempt and two after the second. A
lost lease consumes an attempt and starts backoff from its expiration time.
The third retryable failure or expired lease is recorded as exhausted.
Journal and outbox changes are transactional. If the worker cannot write a
result, the lease remains recoverable and the worker logs a generic database
error. Lease timing uses the system wall clock and assumes a consistent clock
for processes using the same SQLite file.

The retry policy has at-least-once semantics, so a receiver can see
duplicates. Delivery can still exhaust all attempts without reaching the
receiver. A receiver may process a POST before the worker records the result,
or a worker may lose its lease after being paused. Deduplicate by
`Idempotency-Key`, which is derived from the audit ID and result pointer and
is stable across retries and restarts. Reauditing the same call creates a new
audit and new events.

Existing `critical_webhook_journal` rows are retained as history. Old
`started` rows without results have unknown delivery status. They and old
result rows are not replayed. The prior version did not durably bind
historical audits or attempts to a target, so migration does not backfill
historical audits. Upgrade all webhook-enabled replicas to apply atomic
enqueue to every new audit.

Pending events run only while the exact original target string is configured.
Disabling delivery pauses existing work. Changing the URL, including query
credentials, leaves existing pending events parked for the old URL. Restoring
the same URL resumes work, and terminal events stay terminal. Stop old
replicas when retiring a target. The outbox stores a SHA-256 target
fingerprint, not the URL. The journal stores event and audit IDs, result
pointer, attempt, timestamp, coarse outcome and HTTP status where available.
URLs, credentials, response bodies and raw exception messages are excluded
from logs and the journal.
