"""SQLite review journal, sharing the audit store's connection and lock."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import ValidationError

from subpoena.api.review import (
    EDGES,
    Receipt,
    ReviewError,
    ReviewItem,
    Transition,
    TransitionRequest,
    audit_items,
    replay,
    seal_transition,
)
from subpoena.auditor.seal import GENESIS, Authentication, Sealer
from subpoena.models import AuditReport
from subpoena.util import utcnow

REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_journal(
    seq INTEGER PRIMARY KEY CHECK (seq > 0), body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS review_journal_no_update BEFORE UPDATE ON review_journal
    BEGIN SELECT RAISE(ABORT, 'the review journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_journal_no_delete BEFORE DELETE ON review_journal
    BEGIN SELECT RAISE(ABORT, 'the review journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_journal_no_replace BEFORE INSERT ON review_journal
    WHEN EXISTS (SELECT 1 FROM review_journal WHERE seq = NEW.seq)
    BEGIN SELECT RAISE(ABORT, 'the review journal is append-only'); END;
"""


@contextmanager
def _transaction(conn: sqlite3.Connection, *, write: bool = False) -> Iterator[None]:
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    except sqlite3.OperationalError as exc:
        if getattr(exc, "sqlite_errorcode", 0) & 0xFF in (
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_LOCKED,
        ):
            raise ReviewError(503, "review journal is busy; retry after fetching the item") from exc
        raise


def _snapshot(
    conn: sqlite3.Connection,
    key: bytes | None,
    checkpoint: str | None = None,
) -> tuple[dict[str, ReviewItem], list[Receipt], Authentication]:
    sealer = Sealer(key)
    items = {}
    previous = GENESIS
    try:
        for audit_id, chain_hash, body in conn.execute(
            "SELECT audit_id, chain_hash, body FROM audits ORDER BY seq"
        ):
            report = AuditReport.model_validate_json(body)
            if (
                report.audit_id != audit_id
                or report.seal is None
                or report.seal.chain_hash != chain_hash
                or not sealer.verify(report, expected_prev=previous).ok
            ):
                raise ReviewError(500, "source audit ledger verification failed")
            previous = chain_hash
            items.update((item.item_id, item) for item in audit_items(report))
        journal = []
        for seq, body in conn.execute("SELECT seq, body FROM review_journal ORDER BY seq"):
            receipt = Receipt.model_validate_json(body)
            if receipt.sequence != seq:
                raise ReviewError(500, "review journal sequence check failed")
            journal.append(receipt)
    except (ValidationError, TypeError, ValueError) as exc:
        raise ReviewError(500, "invalid stored audit or review data") from exc
    items, authentication = replay(items, journal, key, checkpoint)
    return items, journal, authentication


def list_reviews(
    conn: sqlite3.Connection,
    key: bytes | None,
    checkpoint: str | None,
) -> dict:
    with _transaction(conn):
        items, journal, authentication = _snapshot(conn, key, checkpoint)
        return {
            "items": [item.model_dump(mode="json") for item in items.values()],
            "journal": [receipt.model_dump(mode="json") for receipt in journal],
            "journal_head": journal[-1].hash if journal else GENESIS,
            "authentication": authentication.value,
        }


def transition_review(
    conn: sqlite3.Connection,
    key: bytes | None,
    item_id: str,
    request: TransitionRequest,
    checkpoint: str | None,
) -> Receipt:
    with _transaction(conn, write=True):
        items, journal, authentication = _snapshot(conn, key, checkpoint)
        if authentication is Authentication.UNVERIFIABLE:
            raise ReviewError(503, "review journal signing key is required for writes")
        item = items.get(item_id)
        if item is None:
            raise ReviewError(404, "review item not found")
        if request.expected_head != item.head:
            raise ReviewError(409, "review item changed; fetch it before retrying")
        if request.state not in EDGES[item.state]:
            raise ReviewError(409, "invalid review state transition")
        transition = Transition(
            version=1,
            sequence=len(journal) + 1,
            item_id=item_id,
            previous_item_head=item.head,
            previous_hash=journal[-1].hash if journal else GENESIS,
            from_state=item.state,
            to_state=request.state,
            timestamp=utcnow().isoformat(timespec="microseconds"),
            actor=request.actor,
            reason=request.reason,
            key_id=Sealer(key).key_id,
        )
        receipt = seal_transition(transition, key)
        conn.execute(
            "INSERT INTO review_journal(seq, body) VALUES (?, ?)",
            (receipt.sequence, receipt.model_dump_json()),
        )
        return receipt
