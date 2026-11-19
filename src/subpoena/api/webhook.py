"""Post critical audit results and journal delivery independently of the ledger."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import socket
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import UTC, datetime
from typing import TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from subpoena.models import AuditReport, Severity

log = logging.getLogger(__name__)
_ATTEMPTS = 3
_TIMEOUT = 2.0
Transport = Callable[[str, bytes, str, float], int]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS critical_webhook_journal (
    event_id TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    result_pointer TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    http_status INTEGER,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (event_id, attempt, outcome)
)
"""


class _Event(TypedDict):
    event_type: str
    event_id: str
    audit_id: str
    severity: str
    result_pointer: str
    evidence_pointers: list[str]


class _BlockedDestination(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_url(url: str) -> None:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        valid = (
            url.isascii()
            and all(32 < ord(char) < 127 for char in url)
            and "\\" not in url
            and "#" not in url
            and parts.scheme == "https"
            and parts.netloc.lower() in (host, f"{host}:443")
            and len(host) <= 253
            and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            )
            and re.search(r"\.[a-z][a-z0-9-]*$", host)
            and not host.endswith((".localhost", ".local", ".internal"))
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "Critical webhook requires an HTTPS hostname on port 443 without credentials "
            "or a fragment"
        ) from None


def _post(url: str, payload: bytes, event_id: str, timeout: float) -> int:
    host = urlsplit(url).hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(
        not (ip := ipaddress.ip_address(address[4][0])).is_global or ip.is_multicast
        for address in addresses
    ):
        raise _BlockedDestination
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    request = Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Idempotency-Key": event_id},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except HTTPError as exc:
        exc.close()
        return exc.code


def _events(report: AuditReport) -> Iterator[_Event]:
    for section, results in (("findings", report.findings), ("verdicts", report.verdicts)):
        for index, result in enumerate(results):
            if result.severity is not Severity.CRITICAL:
                continue
            pointer = f"/{section}/{index}"
            event_id = hashlib.sha256(f"{report.audit_id}:{pointer}".encode()).hexdigest()
            yield {
                "event_type": "subpoena.critical.v1",
                "event_id": event_id,
                "audit_id": report.audit_id,
                "severity": result.severity.value,
                "result_pointer": pointer,
                "evidence_pointers": [
                    f"{pointer}/evidence/{i}" for i in range(len(result.evidence))
                ],
            }


class CriticalWebhook:
    def __init__(self, url: str, db_path: str, *, transport: Transport = _post) -> None:
        _validate_url(url)
        if db_path in ("", ":memory:"):
            raise ValueError("Critical webhook requires a file-backed SUBPOENA_DB")
        self._url = url
        self._db_path = db_path
        self._transport = transport
        try:
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute(_SCHEMA)
        except sqlite3.Error:
            raise ValueError("Cannot initialize the critical webhook journal") from None

    def deliver(self, report: AuditReport) -> None:
        for event in _events(report):
            try:
                self._deliver_event(event)
            except sqlite3.Error:
                log.error("Critical webhook journal unavailable for event %s", event["event_id"])

    def _deliver_event(self, event: _Event) -> None:
        event_id = event["event_id"]
        payload = json.dumps(event).encode()
        with closing(sqlite3.connect(self._db_path)) as conn:

            def record(attempt: int, outcome: str, status: int | None = None) -> bool:
                with conn:
                    inserted = conn.execute(
                        "INSERT INTO critical_webhook_journal VALUES (?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(event_id, attempt, outcome) DO NOTHING",
                        (
                            event_id,
                            event["audit_id"],
                            event["result_pointer"],
                            attempt,
                            outcome,
                            status,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                return inserted.rowcount == 1

            for attempt in range(1, _ATTEMPTS + 1):
                if not record(attempt, "started"):
                    return
                status = None
                try:
                    status = self._transport(self._url, payload, event_id, _TIMEOUT)
                except _BlockedDestination:
                    outcome, retry = "blocked_destination", False
                except (TimeoutError, URLError, OSError) as exc:
                    reason = exc.reason if isinstance(exc, URLError) else exc
                    outcome = "timeout" if isinstance(reason, TimeoutError) else "transport_error"
                    retry = True
                except Exception:
                    outcome, retry = "unexpected_transport_error", False
                else:
                    outcome = "delivered" if 200 <= status < 300 else "http_error"
                    retry = status in (408, 429) or 500 <= status < 600
                if retry and attempt == _ATTEMPTS:
                    outcome += "_exhausted"
                record(attempt, outcome, status)
                if not retry:
                    return
