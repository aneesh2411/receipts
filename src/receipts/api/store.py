"""Persistence for ingested calls and the append-only audit ledger."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator

from receipts.auditor.seal import GENESIS, Sealer
from receipts.models import AuditReport, CallRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls(call_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audits(
    seq INTEGER PRIMARY KEY AUTOINCREMENT, audit_id TEXT NOT NULL UNIQUE,
    call_id TEXT NOT NULL, chain_hash TEXT NOT NULL, body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audits_no_update BEFORE UPDATE ON audits
    BEGIN SELECT RAISE(ABORT, 'the audit ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audits_no_delete BEFORE DELETE ON audits
    BEGIN SELECT RAISE(ABORT, 'the audit ledger is append-only'); END;
"""


class AuditStore:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- calls -------------------------------------------------------------- #

    def save_call(self, call: CallRecord) -> bool:
        """Store a call. Returns False if that call id is already stored."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO calls(call_id, body) VALUES (?, ?)",
                (call.call_id, call.model_dump_json()),
            )
            return cur.rowcount == 1

    def get_call(self, call_id: str) -> CallRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM calls WHERE call_id = ?", (call_id,)
            ).fetchone()
        return CallRecord.model_validate_json(row[0]) if row else None

    # -- ledger ------------------------------------------------------------- #

    def head(self) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT chain_hash FROM audits ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else GENESIS

    def append(self, report: AuditReport, sealer: Sealer) -> AuditReport:
        """Seal ``report`` onto the end of the ledger and store it, atomically."""
        with self._lock:
            sealed = sealer.seal(report, self.head())
            assert sealed.seal is not None
            self._conn.execute(
                "INSERT INTO audits(audit_id, call_id, chain_hash, body) VALUES (?, ?, ?, ?)",
                (
                    sealed.audit_id,
                    sealed.call.call_id,
                    sealed.seal.chain_hash,
                    sealed.model_dump_json(),
                ),
            )
        return sealed

    def get_audit(self, audit_id: str) -> AuditReport | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM audits WHERE audit_id = ?", (audit_id,)
            ).fetchone()
        return AuditReport.model_validate_json(row[0]) if row else None

    def audits(self, limit: int | None = None, newest_first: bool = False) -> Iterator[AuditReport]:
        order = "DESC" if newest_first else "ASC"
        sql = f"SELECT body FROM audits ORDER BY seq {order}"  # order is one of two literals
        params: tuple[int, ...] = ()
        if limit is not None:
            sql, params = sql + " LIMIT ?", (limit,)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        for (body,) in rows:
            yield AuditReport.model_validate_json(body)
