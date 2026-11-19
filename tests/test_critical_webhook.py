"""Issue #51. Every receiver and DNS answer stays in process."""

import json
import socket
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from subpoena.api import Settings, app, create_app
from subpoena.api import webhook as hooks

URL = "https://receiver.example.test/hook?key=synthetic-secret"
SCENARIO = "/demo/scenarios/fault-wrong-time"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("webhook tests must never use the network")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


@pytest.fixture
def receiver(monkeypatch, tmp_path):
    calls = []
    results = []
    now = [1000.0]

    def transport(url, body, event_id, timeout):
        calls.append((url, json.loads(body), event_id, timeout))
        result = results.pop(0) if results else 204
        if isinstance(result, Exception):
            raise result
        return result

    worker = None
    original = hooks.CriticalWebhook

    def configure(url, db_path):
        nonlocal worker
        worker = original(url, db_path, transport=transport, clock=lambda: now[0])
        return worker

    monkeypatch.setattr("subpoena.api.app.CriticalWebhook", configure)
    path = tmp_path / "audits.db"
    monkeypatch.setenv("SUBPOENA_CRITICAL_WEBHOOK_URL", URL)
    monkeypatch.setenv("SUBPOENA_DB", str(path))
    client = TestClient(create_app())
    return client, calls, results, path, worker, now


def journal(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(
            "SELECT event_id, audit_id, result_pointer, attempt, outcome, http_status "
            "FROM critical_webhook_journal ORDER BY rowid"
        ).fetchall()


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SUBPOENA_CRITICAL_WEBHOOK_URL", raising=False)
    with TestClient(create_app(Settings.from_env())) as client:
        assert client.post(f"{SCENARIO}/run").status_code == 201
        assert len(list(client.app.state.store.audits())) == 1
        assert client.app.state.store._conn.execute(
            "SELECT count(*) FROM critical_webhook_outbox"
        ).fetchone() == (0,)


def test_noncritical_ignored(receiver):
    client, calls, _, path, worker, _ = receiver
    assert client.post("/demo/scenarios/clean-book/run").status_code == 201
    assert not worker._step()
    assert calls == journal(path) == []


def test_critical_payload_and_repeat_audit(receiver):
    client, calls, _, path, worker, _ = receiver
    call = client.post(f"{SCENARIO}/stage").json()["data"]
    for _ in range(2):
        response = client.post("/audit", json={"call": call})
        assert response.status_code == 201
        report = response.json()["data"]
        assert report["outcome"] == "DISCREPANCIES"
        assert client.get(f"/audit/{report['audit_id']}/report").json()["data"] == report
        assert worker._step()
        url, payload, event_id, timeout = calls[-1]
        assert url == URL
        assert report["verdicts"][0]["severity"] == "CRITICAL"
        assert report["verdicts"][0]["evidence"]
        assert payload == {
            "event_type": "subpoena.critical.v1",
            "event_id": event_id,
            "audit_id": report["audit_id"],
            "severity": "CRITICAL",
            "result_pointer": "/verdicts/0",
            "evidence_pointers": [
                f"/verdicts/0/evidence/{i}" for i in range(len(report["verdicts"][0]["evidence"]))
            ],
        }
        assert timeout == 2.0
    assert len(calls) == 2
    assert calls[0][2] != calls[1][2]
    assert [row[4] for row in journal(path)] == ["started", "delivered"] * 2


def test_retries_and_durable_failure(receiver):
    client, calls, results, path, worker, now = receiver
    results[:] = [TimeoutError(URL), 429, 503]
    response = client.post(f"{SCENARIO}/run")
    assert response.status_code == 201
    report = response.json()["data"]
    assert worker._step()
    assert not worker._step()
    now[0] += 1
    assert worker._step()
    now[0] += 1
    assert not worker._step()
    now[0] += 1
    assert worker._step()
    now[0] += 60
    assert not worker._step()
    assert len(calls) == 3 and all(call == calls[0] for call in calls)
    client.app.state.store.close()
    rows = journal(path)
    assert [(row[3], row[4], row[5]) for row in rows] == [
        (1, "started", None),
        (1, "timeout", None),
        (2, "started", None),
        (2, "http_error", 429),
        (3, "started", None),
        (3, "http_error_exhausted", 503),
    ]
    assert "synthetic-secret" not in repr(rows)
    assert rows[-1][1] == report["audit_id"]
    reopened = TestClient(create_app(Settings(db_path=str(path))))
    assert reopened.get("/ledger/verify").json()["data"]["ok"]
    assert reopened.get(f"/audit/{report['audit_id']}/report").json()["data"] == report


@pytest.mark.parametrize(
    "url",
    [
        "http://receiver.example.test/hook",
        "https://operator:synthetic-secret@receiver.example.test",
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://169.254.169.254/hook",
        "https://metadata.google.internal/hook",
        "https://receiver.example.test:8443/hook",
        "https://receiver.example.test/#fragment",
    ],
)
def test_invalid_configuration(tmp_path, url):
    with pytest.raises(ValueError, match="requires an HTTPS hostname") as exc:
        create_app(Settings(db_path=str(tmp_path / "audits.db"), critical_webhook_url=url))
    assert "synthetic-secret" not in str(exc.value)


def test_enabled_requires_a_durable_store():
    with pytest.raises(ValueError, match="file-backed"):
        create_app(Settings(critical_webhook_url=URL))


def test_critical_standalone_finding_is_delivered(receiver, monkeypatch):
    from subpoena.models import Evidence, Finding, FindingKind, Severity

    original = app.audit_call

    def audit_call(*args, **kwargs):
        report = original(*args, **kwargs)
        finding = Finding(
            finding_id="synthetic finding identifier",
            kind=FindingKind.POLICY_VIOLATION,
            code="synthetic",
            severity=Severity.CRITICAL,
            summary="synthetic finding detail",
            evidence=(Evidence(source="calendar", ref="synthetic private ID", note="private"),),
        )
        return report.model_copy(update={"findings": (finding,)})

    monkeypatch.setattr(app, "audit_call", audit_call)
    client, calls, _, _, worker, _ = receiver
    assert client.post("/demo/scenarios/clean-book/run").status_code == 201
    assert worker._step()
    assert len(calls) == 1
    payload = calls[0][1]
    assert payload["result_pointer"] == "/findings/0"
    assert payload["evidence_pointers"] == ["/findings/0/evidence/0"]
    assert "synthetic" not in repr(payload)


def test_enqueue_failure_rolls_back_audit(receiver):
    client, calls, _, path, worker, _ = receiver
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("""
            CREATE TRIGGER fail_enqueue BEFORE INSERT ON critical_webhook_outbox
            BEGIN SELECT RAISE(ABORT, 'synthetic enqueue error'); END
        """)
    http = TestClient(client.app, raise_server_exceptions=False)
    assert http.post(f"{SCENARIO}/run").status_code == 500
    assert list(client.app.state.store.audits()) == []
    assert not worker._step()
    assert calls == journal(path) == []


@pytest.mark.parametrize("crash_after_send", [False, True])
def test_expired_claim_replays_after_restart(receiver, crash_after_send):
    client, calls, _, path, worker, now = receiver
    report = client.post(f"{SCENARIO}/run").json()["data"]
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        abandoned = worker._claim(conn)
    if crash_after_send:
        worker._transport(URL, abandoned.payload, abandoned.event_id, 2.0)
    restarted = hooks.CriticalWebhook(
        URL, str(path), transport=worker._transport, clock=lambda: now[0]
    )
    assert not restarted._step()
    now[0] += 30
    assert not restarted._step()  # Records lease expiry and schedules backoff.
    assert not restarted._step()
    now[0] += 1
    assert restarted._step()
    # A stale worker cannot overwrite the new result.
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        worker._finish(conn, abandoned, "delivered", False, 204)
    rows = journal(path)
    assert [row[4] for row in rows] == ["started", "lease_expired", "started", "delivered"]
    assert {row[0] for row in rows} == {abandoned.event_id}
    assert {row[1] for row in rows} == {report["audit_id"]}
    assert len(calls) == 1 + crash_after_send
    assert {call[2] for call in calls} == {abandoned.event_id}


def test_three_expired_claims_are_terminal(receiver):
    client, _, _, path, worker, now = receiver
    client.post(f"{SCENARIO}/run")
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        for attempt in range(3):
            assert worker._claim(conn).attempt == attempt + 1
            now[0] += 30
            assert worker._claim(conn) is None
            now[0] += 4
        assert worker._claim(conn) is None
    assert journal(path)[-1][4] == "lease_expired_exhausted"


def test_pending_replay_respects_target_and_legacy_journal(receiver):
    client, calls, _, path, worker, now = receiver
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO critical_webhook_journal VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("old", "old", "/verdicts/0", 1, outcome, None, "old-time")
                for outcome in ("started", "http_error")
            ],
        )
    client.post(f"{SCENARIO}/run")
    matching = hooks.CriticalWebhook(
        URL, str(path), transport=worker._transport, clock=lambda: now[0]
    )
    changed = hooks.CriticalWebhook(
        URL + "&rotate=1", str(path), transport=worker._transport, clock=lambda: now[0]
    )
    assert not changed._step()
    with TestClient(create_app(Settings(db_path=str(path)))):
        assert calls == []
    assert matching._step()
    assert not matching._step()
    assert len(calls) == 1
    assert [r[4] for r in journal(path)] == ["started", "http_error", "started", "delivered"]


def test_workers_contend_for_one_lease(receiver):
    client, calls, _, path, worker, now = receiver
    client.post(f"{SCENARIO}/run")
    entered = threading.Event()
    release = threading.Event()

    def slow(*args):
        entered.set()
        assert release.wait(3)
        return worker._transport(*args)

    other = hooks.CriticalWebhook(URL, str(path), transport=slow, clock=lambda: now[0])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(other._step)
        try:
            assert entered.wait(3)
            assert not worker._step()
        finally:
            release.set()
        assert future.result(timeout=3)
    assert len(calls) == 1
    assert [row[4] for row in journal(path)] == ["started", "delivered"]


def test_lifespan_delivery_does_not_hold_audit_response(receiver):
    client, _, _, path, worker, _ = receiver
    entered = threading.Event()
    release = threading.Event()

    def slow(*_):
        entered.set()
        if not release.wait(3):
            raise TimeoutError
        return 204

    worker._transport = slow
    with client, ThreadPoolExecutor(max_workers=1) as pool:
        try:
            result = pool.submit(client.post, f"{SCENARIO}/run")
            assert entered.wait(2)
            response = result.result(timeout=1)
            assert response.status_code == 201
            assert client.get("/ledger/verify").json()["data"]["ok"]
            assert journal(path)[-1][4] == "started"
        finally:
            release.set()
    assert worker._thread is None
    assert journal(path)[-1][4] == "delivered"


def test_lifespan_replays_pending_and_finishes_terminal_http(receiver, monkeypatch):
    client, _, _, path, _, now = receiver
    assert client.post(f"{SCENARIO}/run").status_code == 201
    entered = threading.Event()

    def redirect(*_):
        entered.set()
        return 307

    worker = hooks.CriticalWebhook(URL, str(path), transport=redirect, clock=lambda: now[0])
    monkeypatch.setattr(app, "CriticalWebhook", lambda *_: worker)
    reopened = create_app(Settings(db_path=str(path), critical_webhook_url=URL))
    with TestClient(reopened):
        assert entered.wait(3)
    now[0] += 60
    assert not worker._step()
    assert [row[4:] for row in journal(path)] == [("started", None), ("http_error", 307)]
