"""Review API, replay integrity and SQLite transaction boundaries."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from subpoena.api import Settings, create_app
from subpoena.api.review import Receipt, ReviewError, TransitionRequest
from subpoena.api.store import AuditStore
from subpoena.auditor.seal import GENESIS

KEY = b"review-test-key"
STATES = ("open", "acknowledged", "pending_verification", "resolved", "disputed")
PATHS = {
    "open": (),
    "acknowledged": ("acknowledged",),
    "pending_verification": ("acknowledged", "pending_verification"),
    "resolved": ("acknowledged", "resolved"),
    "disputed": ("acknowledged", "disputed"),
}
ALLOWED = {
    ("open", "acknowledged"),
    ("acknowledged", "resolved"),
    ("acknowledged", "disputed"),
    ("acknowledged", "pending_verification"),
    ("pending_verification", "resolved"),
    ("pending_verification", "acknowledged"),
    ("pending_verification", "disputed"),
    ("disputed", "open"),
}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.delenv("SUBPOENA_LLM", raising=False)
    return Settings(db_path=str(tmp_path / "audit.sqlite"), api_key="shared", signing_key=KEY)


def _data(response, status=200):
    assert response.status_code == status, response.text
    return response.json()["data"]


def _client(settings):
    return TestClient(
        create_app(settings),
        headers={"X-API-Key": "shared"},
        raise_server_exceptions=False,
    )


def _list(client, checkpoint=None):
    params = {"checkpoint": checkpoint} if checkpoint is not None else {}
    return _data(client.get("/reviews", params=params))


def _payload(head, state="acknowledged", **overrides):
    return {
        "expected_head": head,
        "state": state,
        "actor": "operator",
        "reason": "Reviewed",
        **overrides,
    }


def _transition(client, item, state="acknowledged", **overrides):
    return client.post(
        f"/reviews/{item['item_id']}/transition",
        json=_payload(item["head"], state, **overrides),
    )


@pytest.fixture
def client(settings):
    with _client(settings) as client:
        _data(client.post("/demo/scenarios/fault-wrong-time/run"), 201)
        yield client
        client.app.state.store.close()
        client.app.state.sor.close()


def test_list_sources_lifecycle_and_immutable_audit(client):
    finding_report = _data(client.post("/demo/scenarios/fault-unclaimed-write/run"), 201)
    clean_report = _data(client.post("/demo/scenarios/clean-book/run"), 201)
    initial = _list(client)
    assert initial["journal"] == []
    assert initial["journal_head"] == GENESIS
    assert initial["authentication"] == "unsigned"
    assert all(item["audit_id"] != clean_report["audit_id"] for item in initial["items"])
    item, finding = initial["items"]
    assert item["audit_id"] != finding_report["audit_id"]
    assert item["result_pointer"] == "/verdicts/0"
    assert finding["audit_id"] == finding_report["audit_id"]
    assert finding["result_pointer"] == "/findings/0"
    report_url = f"/audit/{item['audit_id']}/report"
    before = _data(client.get(report_url))
    ledger = _data(client.get("/ledger/verify", params={"strict": True}))
    scorecard = _data(client.get("/scorecard"))
    assert item["audit_chain_hash"] == before["seal"]["chain_hash"]

    previous = GENESIS
    for seq, state in enumerate(
        (
            "acknowledged",
            "disputed",
            "open",
            "acknowledged",
            "pending_verification",
            "acknowledged",
            "pending_verification",
            "resolved",
        ),
        1,
    ):
        start = datetime.now(UTC)
        receipt = _data(_transition(client, item, state, actor="Operator A", reason="Reason é"))
        assert receipt["from_state"] == item["state"]
        assert receipt["previous_item_head"] == item["head"]
        assert receipt["previous_hash"] == previous
        assert receipt["sequence"] == seq
        assert start <= datetime.fromisoformat(receipt["timestamp"]) <= datetime.now(UTC)
        assert receipt["actor"] == "Operator A" and receipt["reason"] == "Reason é"
        snapshot = _list(client, previous)
        assert snapshot["authentication"] == "authenticated"
        assert snapshot["journal"][-1] == receipt
        assert snapshot["journal_head"] == receipt["hash"]
        previous = receipt["hash"]
        item = snapshot["items"][0]
        assert item["state"] == state and item["head"] == receipt["hash"]
        assert item["item_id"] == initial["items"][0]["item_id"]
        assert snapshot["items"][1] == finding

    assert _data(client.get(report_url)) == before
    assert _data(client.get("/ledger/verify", params={"strict": True})) == ledger
    assert ledger["ok"] is True
    assert _data(client.get("/scorecard")) == scorecard


@pytest.mark.parametrize(
    ("source", "target"),
    [(s, t) for s in STATES for t in STATES if (s, t) not in ALLOWED],
)
def test_invalid_edges_leave_no_change(client, source, target):
    for step in PATHS[source]:
        _data(_transition(client, _list(client)["items"][0], step))
    before = _list(client)
    result = _transition(client, before["items"][0], target)
    assert result.status_code == 409
    assert result.json()["error"] == "invalid review state transition"
    assert _list(client) == before


@pytest.mark.parametrize(
    "overrides",
    [
        {"actor": ""},
        {"actor": "  "},
        {"actor": 42},
        {"actor": "x" * 129},
        {"actor": "name\u0000"},
        {"reason": ""},
        {"reason": "   "},
        {"reason": None},
        {"reason": "x" * 2001},
        {"reason": "a\nb"},
        {"expected_head": "bad"},
        {"state": "bogus"},
        {"timestamp": "caller-supplied"},
    ],
)
def test_malformed_input_leaves_no_change(client, overrides):
    before = _list(client)
    item = before["items"][0]
    payload = _payload(item["head"])
    result = client.post(
        f"/reviews/{item['item_id']}/transition",
        json=payload | overrides,
    )
    assert result.status_code == 422
    assert next(iter(overrides)) in result.json()["error"]
    assert _list(client) == before


def test_auth_unknown_and_stale_token(client):
    before = _list(client)
    item = before["items"][0]
    assert client.get("/reviews", headers={"X-API-Key": ""}).status_code == 401
    assert client.get("/reviews", headers={"X-API-Key": "wrong"}).status_code == 401
    assert (
        client.post(
            f"/reviews/{item['item_id']}/transition",
            headers={"X-API-Key": "wrong"},
            json=_payload(item["head"]),
        ).status_code
        == 401
    )
    assert _transition(client, item | {"item_id": "missing"}).status_code == 404
    assert _list(client) == before
    _data(_transition(client, item))
    updated = _list(client)
    assert _transition(client, item, "resolved").status_code == 409
    assert _list(client) == updated


def test_restart(settings):
    with _client(settings) as first:
        _data(first.post("/demo/scenarios/fault-wrong-time/run"), 201)
        _data(_transition(first, _list(first)["items"][0]))
        before = _list(first)
        first.app.state.store.close()
        first.app.state.sor.close()
    with _client(settings) as second:
        assert _list(second, before["journal_head"]) == before
        _data(_transition(second, before["items"][0], "resolved"))
        second.app.state.store.close()
        second.app.state.sor.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor", "another operator"),
        ("reason", "another reason"),
        ("timestamp", "2026-01-01T00:00:00.000000+00:00"),
        ("previous_hash", "a" * 64),
        ("previous_item_head", "a" * 64),
        ("item_id", "a" * 64),
        ("signature", "a" * 64),
        ("signature", None),
        ("sequence", 2),
    ],
)
def test_tampering_fails_list_and_write(client, settings, field, value):
    item = _list(client)["items"][0]
    receipt = _data(_transition(client, item))
    with sqlite3.connect(settings.db_path) as db:
        db.execute("DROP TRIGGER review_journal_no_update")
        db.execute("UPDATE review_journal SET body = ?", (json.dumps(receipt | {field: value}),))
    assert client.get("/reviews").status_code == 500
    assert _transition(client, item, "resolved").status_code == 500


def test_recomputed_hash_does_not_authenticate_changed_receipt(client, settings):
    item = _list(client)["items"][0]
    receipt = _data(_transition(client, item, reason="Original é"))
    payload = {
        field: value for field, value in receipt.items() if field not in ("hash", "signature")
    }
    prefix = b"subpoena.review.transition.v1:"

    def hash_payload():
        return hashlib.sha256(
            prefix + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()

    assert hash_payload() == receipt["hash"]
    assert (
        hmac.new(
            KEY, b"subpoena.review.signature.v1:" + hash_payload().encode(), "sha256"
        ).hexdigest()
        == receipt["signature"]
    )
    payload["reason"] = "Changed"
    rewritten = payload | {"hash": hash_payload(), "signature": receipt["signature"]}
    with sqlite3.connect(settings.db_path) as db:
        db.execute("DROP TRIGGER review_journal_no_update")
        db.execute("UPDATE review_journal SET body = ?", (json.dumps(rewritten),))
    assert client.get("/reviews").json()["error"] == "review journal signature check failed"
    store = client.app.state.store
    assert store.list_reviews(None)["authentication"] == "unverifiable"
    with pytest.raises(ReviewError, match="does not contain"):
        store.list_reviews(None, receipt["hash"])


def test_global_journal_links_different_items_without_invalidating_item_heads(client):
    _data(client.post("/demo/scenarios/fault-phantom-booking/run"), 201)
    first_item, second_item, *_ = _list(client)["items"]
    first = _data(_transition(client, first_item))
    second = _data(_transition(client, second_item))
    assert second["sequence"] == 2
    assert second["previous_hash"] == first["hash"]
    assert second["previous_item_head"] == second_item["item_id"]
    assert _list(client)["journal"] == [first, second]


def test_checkpoint_detects_tail_deletion_and_chain_detects_interior_deletion(client, settings):
    first = _data(_transition(client, _list(client)["items"][0]))
    second = _data(_transition(client, _list(client)["items"][0], "disputed"))
    with sqlite3.connect(settings.db_path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM review_journal")
        db.execute("DROP TRIGGER review_journal_no_delete")
        db.execute("DELETE FROM review_journal WHERE seq = 2")
    assert _list(client)["journal_head"] == first["hash"]
    assert client.get("/reviews", params={"checkpoint": second["hash"]}).status_code == 409
    item = _list(client)["items"][0]
    result = client.post(
        f"/reviews/{item['item_id']}/transition",
        params={"checkpoint": second["hash"]},
        json=_payload(item["head"], "resolved"),
    )
    assert result.status_code == 409
    assert _list(client)["journal_head"] == first["hash"]
    with sqlite3.connect(settings.db_path) as db:
        db.execute("DELETE FROM review_journal")
        db.execute("INSERT INTO review_journal VALUES (2, ?)", (json.dumps(second),))
    assert client.get("/reviews").status_code == 500


def test_tampered_source_audit_is_rejected(client, settings):
    with sqlite3.connect(settings.db_path) as db:
        db.execute("DROP TRIGGER audits_no_update")
        body = json.loads(db.execute("SELECT body FROM audits").fetchone()[0])
        body["verdicts"][0]["summary"] = "changed"
        db.execute("UPDATE audits SET body = ?", (json.dumps(body),))
    assert client.get("/reviews").json()["error"] == "source audit ledger verification failed"


def test_unsigned_and_signed_without_verification_key(client, settings):
    item = _list(client)["items"][0]
    signed = _data(_transition(client, item))
    store = client.app.state.store
    assert store.list_reviews(None)["authentication"] == "unverifiable"
    with pytest.raises(ReviewError, match="signing key is required"):
        store.transition_review(
            None,
            item["item_id"],
            TransitionRequest(**_payload(signed["hash"], "resolved")),
        )
    with pytest.raises(ReviewError, match="source audit ledger"):
        store.list_reviews(b"wrong-key")

    unsigned_settings = Settings(db_path=settings.db_path + ".unsigned", api_key="shared")
    with _client(unsigned_settings) as unsigned:
        _data(unsigned.post("/demo/scenarios/fault-wrong-time/run"), 201)
        receipt = _data(_transition(unsigned, _list(unsigned)["items"][0]))
        assert receipt["signature"] is None and receipt["key_id"] is None
        assert _list(unsigned, receipt["hash"])["authentication"] == "unsigned"
        unsigned.app.state.store.close()
        unsigned.app.state.sor.close()


def test_failed_insert_rolls_back_and_allows_retry(client, settings):
    before = _list(client)
    with sqlite3.connect(settings.db_path) as db:
        db.execute("""
            CREATE TRIGGER fail_receipt AFTER INSERT ON review_journal
            BEGIN SELECT RAISE(FAIL, 'synthetic receipt failure'); END
        """)
    assert _transition(client, before["items"][0]).status_code == 500
    assert _list(client) == before
    with sqlite3.connect(settings.db_path) as db:
        db.execute("DROP TRIGGER fail_receipt")
    receipt = _data(_transition(client, before["items"][0]))
    assert receipt["sequence"] == 1


def test_concurrent_writes_on_separate_connections_have_one_winner(client, settings):
    item = _list(client)["items"][0]
    ready = Barrier(2)

    def write():
        store = AuditStore(settings.db_path)
        try:
            ready.wait(timeout=5)
            return store.transition_review(
                KEY,
                item["item_id"],
                TransitionRequest(**_payload(item["head"])),
            )
        except ReviewError as exc:
            return exc.status
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [task.result() for task in [pool.submit(write), pool.submit(write)]]
    assert outcomes.count(409) == 1
    [winner] = [receipt for receipt in outcomes if isinstance(receipt, Receipt)]
    assert _list(client)["journal"] == [winner.model_dump(mode="json")]
