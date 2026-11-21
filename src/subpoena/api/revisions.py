"""Verdict revision journal.

When new evidence revises a verdict, the revision is itself a record: the old
verdict, the new verdict, the evidence that forced the change, and the time.
Revisions live in their own append-only, hash-chained (and optionally signed)
journal beside the review journal, so a rewritten history is detectable on
replay. A revision never edits the original audit: the ledger stays immutable
and the revision points at it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime
from typing import Literal

from pydantic import StrictInt, ValidationError

from subpoena.api.review import Hash, KeyID, ReviewError, ReviewModel, audit_items
from subpoena.auditor.seal import GENESIS, Authentication, Sealer
from subpoena.models import AuditReport, VerdictStatus
from subpoena.util import utcnow

REVISION_SCHEMA = """
CREATE TABLE IF NOT EXISTS revision_journal(
    seq INTEGER PRIMARY KEY CHECK (seq > 0), body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS revision_journal_no_update BEFORE UPDATE ON revision_journal
    BEGIN SELECT RAISE(ABORT, 'the revision journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS revision_journal_no_delete BEFORE DELETE ON revision_journal
    BEGIN SELECT RAISE(ABORT, 'the revision journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS revision_journal_no_replace BEFORE INSERT ON revision_journal
    WHEN EXISTS (SELECT 1 FROM revision_journal WHERE seq = NEW.seq)
    BEGIN SELECT RAISE(ABORT, 'the revision journal is append-only'); END;
"""


class Revision(ReviewModel):
    version: Literal[1]
    sequence: StrictInt
    item_id: Hash  # the review item naming the revised verdict
    audit_id: str  # the audit whose verdict was revised
    claim_id: str
    from_status: VerdictStatus
    to_status: VerdictStatus
    source: Literal["recheck", "reaudit"]
    evidence: str  # what new evidence forced the change
    timestamp: str
    previous_hash: Hash
    key_id: KeyID | None


class RevisionReceipt(Revision):
    hash: Hash
    signature: Hash | None


def _digest(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(f"subpoena.revision.v1:{canonical}".encode("ascii")).hexdigest()


def _sign(key: bytes, digest: str) -> str:
    return hmac.new(key, f"subpoena.revision.signature.v1:{digest}".encode(), "sha256").hexdigest()


def seal_revision(revision: Revision, key: bytes | None) -> RevisionReceipt:
    body = revision.model_dump(mode="json")
    digest = _digest(body)
    return RevisionReceipt(**body, hash=digest, signature=_sign(key, digest) if key else None)


def record_revision(
    conn: sqlite3.Connection,
    key: bytes | None,
    *,
    item_id: str,
    audit_id: str,
    claim_id: str,
    from_status: VerdictStatus,
    to_status: VerdictStatus,
    source: Literal["recheck", "reaudit"],
    evidence: str,
) -> RevisionReceipt:
    """Append one revision to the journal. Call inside a write transaction."""
    (count,) = conn.execute("SELECT COUNT(*) FROM revision_journal").fetchone()
    row = conn.execute("SELECT body FROM revision_journal ORDER BY seq DESC LIMIT 1").fetchone()
    previous = GENESIS
    if row is not None:
        previous = RevisionReceipt.model_validate_json(row[0]).hash
    revision = Revision(
        version=1,
        sequence=count + 1,
        item_id=item_id,
        audit_id=audit_id,
        claim_id=claim_id,
        from_status=from_status,
        to_status=to_status,
        source=source,
        evidence=evidence,
        timestamp=utcnow().isoformat(timespec="microseconds"),
        previous_hash=previous,
        key_id=Sealer(key).key_id,
    )
    receipt = seal_revision(revision, key)
    conn.execute(
        "INSERT INTO revision_journal(seq, body) VALUES (?, ?)",
        (receipt.sequence, receipt.model_dump_json()),
    )
    return receipt


def _verify(journal: list[RevisionReceipt], key: bytes | None) -> Authentication:
    previous = GENESIS
    expected_key_id = Sealer(key).key_id
    journal_key_id = journal[0].key_id if journal else None
    for sequence, receipt in enumerate(journal, start=1):
        body = receipt.model_dump(mode="json", exclude={"hash", "signature"})
        if (
            receipt.sequence != sequence
            or receipt.previous_hash != previous
            or receipt.hash != _digest(body)
            or receipt.key_id != journal_key_id
            or (receipt.signature is None) != (receipt.key_id is None)
        ):
            raise ReviewError(500, "revision journal integrity check failed")
        try:
            timestamp = datetime.fromisoformat(receipt.timestamp)
            if (
                timestamp.tzinfo != UTC
                or timestamp.isoformat(timespec="microseconds") != receipt.timestamp
            ):
                raise ValueError("expected canonical UTC timestamp")
        except ValueError as exc:
            raise ReviewError(500, "revision journal timestamp is invalid") from exc
        if key and (
            receipt.key_id != expected_key_id
            or receipt.signature is None
            or not hmac.compare_digest(receipt.signature, _sign(key, receipt.hash))
        ):
            raise ReviewError(500, "revision journal signature check failed")
        previous = receipt.hash
    if journal_key_id is None:
        return Authentication.UNSIGNED
    return Authentication.AUTHENTICATED if key else Authentication.UNVERIFIABLE


def list_revisions(conn: sqlite3.Connection, key: bytes | None) -> dict:
    journal: list[RevisionReceipt] = []
    try:
        for seq, body in conn.execute("SELECT seq, body FROM revision_journal ORDER BY seq"):
            receipt = RevisionReceipt.model_validate_json(body)
            if receipt.sequence != seq:
                raise ReviewError(500, "revision journal sequence check failed")
            journal.append(receipt)
    except (ValidationError, TypeError, ValueError) as exc:
        raise ReviewError(500, "invalid stored revision data") from exc
    authentication = _verify(journal, key)
    return {
        "revisions": [r.model_dump(mode="json") for r in journal],
        "journal_head": journal[-1].hash if journal else GENESIS,
        "authentication": authentication.value,
    }


def _item_id(report: AuditReport, verdict_index: int) -> str:
    pointer = f"/verdicts/{verdict_index}"
    for item in audit_items(report):
        if item.result_pointer == pointer:
            return item.item_id
    # A VERIFIED verdict has no review item; name the one it would have had.
    source = {
        "audit_id": report.audit_id,
        "audit_chain_hash": report.seal.chain_hash if report.seal else "",
        "result_pointer": pointer,
    }
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(f"subpoena.review.item.v1:{canonical}".encode("ascii")).hexdigest()


def record_reaudit_revisions(
    conn: sqlite3.Connection,
    key: bytes | None,
    *,
    old: AuditReport,
    new: AuditReport,
) -> list[RevisionReceipt]:
    """Record one revision per claim whose verdict changed between two audits
    of the same call. Call inside the same write transaction as the append."""
    assert old.call.call_id == new.call.call_id
    assert new.seal is not None
    new_by_claim = {v.claim.claim_id: v for v in new.verdicts}
    receipts = []
    for index, old_verdict in enumerate(old.verdicts):
        new_verdict = new_by_claim.get(old_verdict.claim.claim_id)
        if new_verdict is None or new_verdict.status == old_verdict.status:
            continue
        receipts.append(
            record_revision(
                conn,
                key,
                item_id=_item_id(old, index),
                audit_id=old.audit_id,
                claim_id=old_verdict.claim.claim_id,
                from_status=old_verdict.status,
                to_status=new_verdict.status,
                source="reaudit",
                evidence=f"Re-audit {new.audit_id} (chain "
                f"{new.seal.chain_hash[:16]}...) of the same call reached a "
                "different verdict.",
            )
        )
    return receipts


def golden_candidate(receipt: RevisionReceipt) -> dict:
    """A revision as golden-dataset material: the first verdict did not survive
    new evidence, so the corrected expectation is worth pinning."""
    return {
        "claim_id": receipt.claim_id,
        "audit_id": receipt.audit_id,
        "expected_status": receipt.to_status.value,
        "previously": receipt.from_status.value,
        "source": receipt.source,
        "note": "The first verdict did not survive new evidence. Pin the corrected "
        "expectation in a golden scenario and review what the audit missed.",
    }
