"""Post critical audit results and journal delivery independently of the ledger."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict
from urllib.parse import urlsplit

from subpoena.api.webhook_transport import BlockedDestination, CertificateError, post, supported
from subpoena.models import AuditReport, Severity

log = logging.getLogger(__name__)
_ATTEMPTS = 3
_TIMEOUT = 2.0
_LEASE = 30.0
_POLL = 0.25
_DB_TIMEOUT = 0.25
Transport = Callable[[str, bytes, str, float], int]

SCHEMA = """
CREATE TABLE IF NOT EXISTS critical_webhook_journal (
    event_id TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    result_pointer TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    http_status INTEGER,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (event_id, attempt, outcome)
);
CREATE TABLE IF NOT EXISTS critical_webhook_outbox (
    event_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL,
    result_pointer TEXT NOT NULL,
    payload BLOB NOT NULL,
    target_key TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    due_at REAL NOT NULL,
    lease_id TEXT,
    lease_until REAL,
    terminal INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS critical_webhook_due
    ON critical_webhook_outbox(target_key, terminal, due_at);
"""


class _Event(TypedDict):
    event_type: str
    event_id: str
    audit_id: str
    severity: str
    result_pointer: str
    evidence_pointers: list[str]


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


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Acquire the write reservation before reading state that determines a write."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


@dataclass(frozen=True)
class _Claim:
    event_id: str
    audit_id: str
    pointer: str
    payload: bytes
    attempt: int
    lease_id: str


def _journal(conn, event_id, audit_id, pointer, attempt, outcome, now, status=None):
    conn.execute(
        "INSERT INTO critical_webhook_journal VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            event_id,
            audit_id,
            pointer,
            attempt,
            outcome,
            status,
            datetime.fromtimestamp(now, UTC).isoformat(),
        ),
    )


def _backoff(attempt: int) -> float:
    return float(2 ** (attempt - 1))


class CriticalWebhook:
    def __init__(
        self, url: str, db_path: str, *, transport: Transport = post, clock=time.time
    ) -> None:
        _validate_url(url)
        if db_path in ("", ":memory:"):
            raise ValueError("Critical webhook requires a file-backed SUBPOENA_DB")
        if not supported():
            raise ValueError("Critical webhook requires POSIX interval timer support")
        self._url = url
        self._target = hashlib.sha256(url.encode()).hexdigest()
        self._db_path = db_path
        self._transport = transport
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def enqueue(self, conn: sqlite3.Connection, report: AuditReport) -> None:
        now = self._clock()
        conn.executemany(
            "INSERT INTO critical_webhook_outbox "
            "(event_id, audit_id, result_pointer, payload, target_key, due_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                (
                    e["event_id"],
                    e["audit_id"],
                    e["result_pointer"],
                    json.dumps(e).encode(),
                    self._target,
                    now,
                )
                for e in _events(report)
            ),
        )

    def _claim(self, conn: sqlite3.Connection) -> _Claim | None:
        # Avoid taking SQLite's write reservation on idle polling.
        ready = (
            "target_key = ? AND terminal = 0 AND due_at <= ? "
            "AND (lease_until IS NULL OR lease_until <= ?)"
        )
        query = (
            "SELECT event_id, audit_id, result_pointer, payload, attempt, lease_until "
            f"FROM critical_webhook_outbox WHERE {ready} ORDER BY due_at, rowid LIMIT 1"
        )
        now = self._clock()
        if conn.execute(query, (self._target, now, now)).fetchone() is None:
            return None
        with write_transaction(conn):
            now = self._clock()
            row = conn.execute(query, (self._target, now, now)).fetchone()
            if row is None:
                return None
            event_id, audit_id, pointer, payload, attempt, expired = row
            if expired is not None:
                terminal = attempt >= _ATTEMPTS
                outcome = "lease_expired_exhausted" if terminal else "lease_expired"
                _journal(conn, event_id, audit_id, pointer, attempt, outcome, now)
                conn.execute(
                    "UPDATE critical_webhook_outbox SET lease_id = NULL, lease_until = NULL, "
                    "terminal = ?, due_at = ? WHERE event_id = ?",
                    (terminal, expired + _backoff(attempt), event_id),
                )
                return None

            attempt += 1
            lease_id = uuid.uuid4().hex
            conn.execute(
                "UPDATE critical_webhook_outbox SET attempt = ?, lease_id = ?, lease_until = ? "
                "WHERE event_id = ?",
                (attempt, lease_id, now + _LEASE, event_id),
            )
            _journal(conn, event_id, audit_id, pointer, attempt, "started", now)
            return _Claim(event_id, audit_id, pointer, payload, attempt, lease_id)

    def _finish(
        self,
        conn: sqlite3.Connection,
        claim: _Claim,
        outcome: str,
        retry: bool,
        status: int | None,
    ) -> None:
        with write_transaction(conn):
            now = self._clock()
            terminal = not retry or claim.attempt >= _ATTEMPTS
            updated = conn.execute(
                "UPDATE critical_webhook_outbox SET terminal = ?, due_at = ?, "
                "lease_id = NULL, lease_until = NULL WHERE event_id = ? AND lease_id = ? "
                "AND lease_until > ?",
                (terminal, now + _backoff(claim.attempt), claim.event_id, claim.lease_id, now),
            )
            if updated.rowcount:
                if terminal and retry:
                    outcome += "_exhausted"
                _journal(
                    conn,
                    claim.event_id,
                    claim.audit_id,
                    claim.pointer,
                    claim.attempt,
                    outcome,
                    now,
                    status,
                )

    def _step(self) -> bool:
        with closing(
            sqlite3.connect(self._db_path, isolation_level=None, timeout=_DB_TIMEOUT)
        ) as conn:
            claim = self._claim(conn)
            if claim is None:
                return False
            status = None
            try:
                status = self._transport(self._url, claim.payload, claim.event_id, _TIMEOUT)
            except BlockedDestination:
                outcome, retry = "blocked_destination", False
            except CertificateError:
                outcome, retry = "certificate_error", False
            except TimeoutError:
                outcome, retry = "timeout", True
            except OSError:
                outcome, retry = "transport_error", True
            except Exception:
                outcome, retry = "unexpected_transport_error", False
            else:
                outcome = "delivered" if 200 <= status < 300 else "http_error"
                retry = status in (408, 429) or 500 <= status < 600
            self._finish(conn, claim, outcome, retry, status)
            return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self._step():
                    continue
            except sqlite3.Error:
                log.error("Critical webhook worker could not access the outbox")
            self._stop.wait(_POLL)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Critical webhook worker is already running")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="subpoena-webhook", daemon=False)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=_TIMEOUT + 2 * _DB_TIMEOUT + 1)
            if self._thread.is_alive():
                raise RuntimeError(
                    "Critical webhook worker did not stop within its shutdown budget"
                )
            self._thread = None
