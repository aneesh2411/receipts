"""Issue #51. Every receiver and DNS answer stays in process."""

import json
import socket
import sqlite3
import urllib.request
from contextlib import closing
from email.message import Message
from io import BytesIO

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

    def transport(url, body, event_id, timeout):
        calls.append((url, json.loads(body), event_id, timeout))
        result = results.pop(0) if results else 204
        if isinstance(result, Exception):
            raise result
        return result

    original = hooks.CriticalWebhook

    def configure(url, db_path):
        return original(url, db_path, transport=transport)

    monkeypatch.setattr("subpoena.api.app.CriticalWebhook", configure)
    path = tmp_path / "audits.db"
    monkeypatch.setenv("SUBPOENA_CRITICAL_WEBHOOK_URL", URL)
    monkeypatch.setenv("SUBPOENA_DB", str(path))
    client = TestClient(create_app())
    return client, calls, results, path


def journal(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(
            "SELECT event_id, audit_id, result_pointer, attempt, outcome, http_status "
            "FROM critical_webhook_journal ORDER BY rowid"
        ).fetchall()


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SUBPOENA_CRITICAL_WEBHOOK_URL", raising=False)
    client = TestClient(create_app(Settings.from_env()))
    assert client.post(f"{SCENARIO}/run").status_code == 201


def test_noncritical_ignored(receiver):
    client, calls, _, path = receiver
    assert client.post("/demo/scenarios/clean-book/run").status_code == 201
    assert calls == journal(path) == []


def test_critical_payload_and_repeat_audit(receiver):
    client, calls, _, path = receiver
    call = client.post(f"{SCENARIO}/stage").json()["data"]
    for _ in range(2):
        response = client.post("/audit", json={"call": call})
        assert response.status_code == 201
        report = response.json()["data"]
        assert report["outcome"] == "DISCREPANCIES"
        assert client.get(f"/audit/{report['audit_id']}/report").json()["data"] == report
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
    client, calls, results, path = receiver
    results[:] = [TimeoutError(URL), 429, 503]
    response = client.post(f"{SCENARIO}/run")
    assert response.status_code == 201
    report = response.json()["data"]
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


def test_same_report_is_not_redelivered(receiver):
    client, calls, _, path = receiver
    report_id = client.post(f"{SCENARIO}/run").json()["data"]["audit_id"]
    report = client.app.state.store.get_audit(report_id)
    hooks.CriticalWebhook(URL, str(path), transport=lambda *args: pytest.fail("duplicate")).deliver(
        report
    )
    assert len(calls) == 1


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


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_real_transport_rejects_nonpublic_dns(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(0, 0, 0, "", (address, 443))])
    with pytest.raises(hooks._BlockedDestination):
        hooks._post(URL, b"{}", "synthetic-event", 2.0)


@pytest.mark.parametrize("status", [302, 307, 400])
def test_real_transport_does_not_redirect_or_retry_terminal_http(monkeypatch, tmp_path, status):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(0, 0, 0, "", ("8.8.8.8", 443))])
    requests = []

    def respond(self, request):
        requests.append(request)
        headers = Message()
        headers["Location"] = "https://other.example.test/"
        response = urllib.response.addinfourl(BytesIO(b""), headers, request.full_url, status)
        response.msg = "synthetic response"
        return response

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", respond)
    path = tmp_path / "audits.db"
    client = TestClient(create_app(Settings(db_path=str(path), critical_webhook_url=URL)))
    assert client.post(f"{SCENARIO}/run").status_code == 201
    assert [r.full_url for r in requests] == [URL]
    assert requests[0].get_method() == "POST"
    assert requests[0].get_header("Idempotency-key") == journal(path)[-1][0]
    assert journal(path)[-1][3:] == (1, "http_error", status)


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
    client, calls, _, _ = receiver
    assert client.post("/demo/scenarios/clean-book/run").status_code == 201
    assert len(calls) == 1
    payload = calls[0][1]
    assert payload["result_pointer"] == "/findings/0"
    assert payload["evidence_pointers"] == ["/findings/0/evidence/0"]
    assert "synthetic" not in repr(payload)
