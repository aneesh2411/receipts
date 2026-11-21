"""Verdict revision journal: a re-audit that changes a verdict records the
revision itself; the chain verifies and stays append-only."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from subpoena.api.review import ReviewError
from subpoena.api.revisions import _verify, golden_candidate
from subpoena.api.store import AuditStore
from subpoena.auditor.seal import GENESIS, Sealer
from subpoena.models import HandoffCreated, VerdictStatus
from subpoena.scenarios.world import CALL_START, ROSTER
from subpoena.suspect import AGENT_ID

KEY = b"revision-test-key"
CALLER = ROSTER[0]
CREATED = CALL_START + timedelta(seconds=5)


def _audits(clinic):
    """Two audits of one call: the ticket lands late, so the second revises
    the first audit's NOT_FOUND to VERIFIED."""
    call = clinic.call(
        claims=[HandoffCreated(claim_id="c1", turn_index=0, patient=CALLER, priority="urgent")]
    )
    first = clinic.audit(call)
    assert first.verdicts[0].status is VerdictStatus.NOT_FOUND
    agent = clinic.as_actor(f"{AGENT_ID}:call-test", CREATED)
    agent.tickets.create_ticket(
        patient_id=clinic.patient(CALLER).id, summary="call back about billing", priority="urgent"
    )
    second = clinic.audit(call).model_copy(update={"audit_id": "aud-second"})
    assert second.verdicts[0].status is VerdictStatus.VERIFIED
    return first, second


def test_reaudit_records_a_signed_revision(clinic) -> None:
    first, second = _audits(clinic)
    store = AuditStore()
    try:
        store.append(first, Sealer(KEY), revision_key=KEY)
        assert store.list_revisions(KEY)["revisions"] == []
        store.append(second, Sealer(KEY), revision_key=KEY)
        data = store.list_revisions(KEY)
        (revision,) = data["revisions"]
        assert revision["claim_id"] == "c1"
        assert revision["audit_id"] == first.audit_id
        assert revision["from_status"] == "NOT_FOUND"
        assert revision["to_status"] == "VERIFIED"
        assert revision["source"] == "reaudit"
        assert "aud-second" in revision["evidence"]
        assert revision["previous_hash"] == GENESIS
        assert data["journal_head"] == revision["hash"]
        assert data["authentication"] == "authenticated"
    finally:
        store.close()


def test_unchanged_verdicts_record_nothing(clinic) -> None:
    call = clinic.call(
        claims=[HandoffCreated(claim_id="c1", turn_index=0, patient=CALLER, priority="urgent")]
    )
    first = clinic.audit(call)
    again = clinic.audit(call).model_copy(update={"audit_id": "aud-again"})
    store = AuditStore()
    try:
        store.append(first, Sealer(KEY), revision_key=KEY)
        store.append(again, Sealer(KEY), revision_key=KEY)
        assert store.list_revisions(KEY)["revisions"] == []
    finally:
        store.close()


def test_unsigned_journal_says_so(clinic) -> None:
    first, second = _audits(clinic)
    store = AuditStore()
    try:
        store.append(first, Sealer())
        store.append(second, Sealer())
        data = store.list_revisions(None)
        assert len(data["revisions"]) == 1
        assert data["authentication"] == "unsigned"
        assert data["revisions"][0]["signature"] is None
    finally:
        store.close()


def test_a_wrong_key_fails_verification(clinic) -> None:
    first, second = _audits(clinic)
    store = AuditStore()
    try:
        store.append(first, Sealer(KEY), revision_key=KEY)
        store.append(second, Sealer(KEY), revision_key=KEY)
        with pytest.raises(ReviewError, match="signature check failed"):
            store.list_revisions(b"the-wrong-key")
    finally:
        store.close()


def test_a_tampered_receipt_fails_verification(clinic) -> None:
    first, second = _audits(clinic)
    store = AuditStore()
    try:
        store.append(first, Sealer(KEY), revision_key=KEY)
        store.append(second, Sealer(KEY), revision_key=KEY)
        (revision,) = store.list_revisions(KEY)["revisions"]
        from subpoena.api.revisions import RevisionReceipt

        receipt = RevisionReceipt(**revision)
        tampered = receipt.model_copy(update={"from_status": VerdictStatus.VERIFIED})
        with pytest.raises(ReviewError, match="integrity check failed"):
            _verify([tampered], KEY)
    finally:
        store.close()


def test_the_journal_is_append_only(clinic) -> None:
    first, second = _audits(clinic)
    store = AuditStore()
    try:
        store.append(first, Sealer(KEY), revision_key=KEY)
        store.append(second, Sealer(KEY), revision_key=KEY)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._conn.execute("UPDATE revision_journal SET body = '{}' WHERE seq = 1")
    finally:
        store.close()


def test_revision_feeds_a_golden_candidate(clinic) -> None:
    first, second = _audits(clinic)
    store = AuditStore()
    try:
        store.append(first, Sealer(KEY), revision_key=KEY)
        store.append(second, Sealer(KEY), revision_key=KEY)
        (revision,) = store.list_revisions(KEY)["revisions"]
        from subpoena.api.revisions import RevisionReceipt

        candidate = golden_candidate(RevisionReceipt(**revision))
        assert candidate["claim_id"] == "c1"
        assert candidate["expected_status"] == "VERIFIED"
        assert candidate["previously"] == "NOT_FOUND"
        assert candidate["source"] == "reaudit"
    finally:
        store.close()
