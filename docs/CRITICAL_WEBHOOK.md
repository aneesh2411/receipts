# Critical audit webhook

Webhook delivery is disabled by default. Deployment operators can set
`SUBPOENA_CRITICAL_WEBHOOK_URL` (or `Settings.critical_webhook_url`) with a
file-backed `SUBPOENA_DB`. An unset or empty environment variable disables
delivery. Invalid configuration fails at application startup with a generic
error. Use a trusted HTTPS hostname on port 443 without embedded credentials
or fragments. Keep the target URL in deployment configuration. URLs and
response bodies are excluded from the delivery journal and application errors.

The API attempts delivery synchronously after committing each sealed report
from `POST /audit` or `POST /demo/scenarios/{id}/run`. Read endpoints, the
standalone CLI demo and offline eval never send alerts. The `serve` command
uses the API behavior. Each critical standalone finding or claim verdict
produces one POST. Delivery outcomes are independent of the audit verdict,
seal, and response status. The response can be delayed by delivery.

The JSON contains the event type (`subpoena.critical.v1`), event ID, audit ID,
severity, and JSON Pointers for the result and its evidence entries. Resolve
the pointers against the report object in `data` from the authorized
`GET /audit/{audit_id}/report` response. For example, `/verdicts/0/evidence/0`
identifies the first evidence entry of the first verdict. The receiver gets
no transcript, free text, claim fields, evidence IDs from source systems,
or record contents.

Each event has at most three immediate attempts with a two-second socket
timeout per blocking operation. DNS resolution and total elapsed request
time are not covered by that socket timeout. A 2xx response succeeds.
HTTP 408, 429, 5xx, and connection or timeout errors retry. Other HTTP
statuses, blocked destinations, and unexpected transport errors are terminal.
Redirects are never followed and environment proxies are disabled. The
transport rejects nonpublic or multicast DNS answers before sending. This
check does not pin the connection to the checked address. DNS changes and
deployment routing can bypass the check, so production deployments must
enforce trusted destinations through DNS and network egress controls.

The SQLite table `critical_webhook_journal` records an event ID, audit ID,
result pointer, attempt number, UTC timestamp, and outcome. Each `started`
row commits before its POST. A second row captures the result, including
the HTTP status when available and an exhaustion suffix on the last
retryable failure. Journal I/O failures log the event ID and stop that
event's delivery. An audit remains committed. A process crash before
journaling can leave an audit with no webhook rows. A crash after
`started` can leave the result unknown. There is no background replay.

The event ID is derived from the audit ID and result pointer and is sent
as the `Idempotency-Key` header. Receivers can deduplicate retries with
that key, including after a response is lost. A report with an existing
first attempt is not resent. Reauditing the same call creates a new audit
and new event IDs.
