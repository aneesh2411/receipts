import json
import subprocess
import sys
from pathlib import Path

import pytest

from subpoena.auditor.seal import Sealer
from subpoena.models import AuditReport

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "docs" / "demo" / "data" / "audit-aud-clean-family-two-bookings.json"
REPORT_ID = "aud-clean-family-two-bookings"
DEMO_KEY = "subpoena-pages-demo"


def run_verifier(*paths, key=DEMO_KEY):
    command = [sys.executable, str(ROOT / "scripts" / "verify_seal.py"), *map(str, paths)]
    if key is not None:
        command.extend(["--key", key])
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)


@pytest.mark.parametrize(
    ("key", "authentication"),
    [(DEMO_KEY, "authenticated"), (None, "unverifiable")],
)
def test_published_report(key, authentication):
    result = run_verifier(EXPORT, key=key)
    assert result.returncode == 0, result.stdout + result.stderr
    status, verdict = result.stdout.splitlines()
    assert f"Report {REPORT_ID!r} receipts=3 integrity=intact" in status
    assert f"authentication={authentication}" in status
    assert verdict == "VERDICT PASS (whole-report verification, 1/1 reports passed)"


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ("edit claim", "integrity=altered"),
        ("drop receipt", "integrity=altered"),
        ("reorder receipts", "integrity=altered"),
        ("drop default field", "integrity=altered"),
        ("wrong key", "signature is invalid"),
        ("missing signature", "signature is missing"),
        ("non-genesis seal", "not linked to the expected previous report"),
    ],
)
def test_rejects_tampered_report(tmp_path, tamper, expected):
    payload = json.loads(EXPORT.read_text(encoding="utf-8"))
    key = DEMO_KEY
    if tamper == "edit claim":
        payload["verdicts"][0]["claim"]["provider"] = "Dr. Edited"
    elif tamper == "drop receipt":
        payload["verdicts"].pop()
    elif tamper == "reorder receipts":
        payload["verdicts"].reverse()
    elif tamper == "drop default field":
        del payload["extraction"]["detail"]
    elif tamper == "wrong key":
        key = "wrong"
    elif tamper == "missing signature":
        del payload["seal"]["signature"]
    elif tamper == "non-genesis seal":
        report = AuditReport.model_validate(payload)
        payload = Sealer(DEMO_KEY.encode()).seal(report, prev_hash="a" * 64).model_dump(mode="json")
    path = tmp_path / "export.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = run_verifier(path, key=key)

    assert result.returncode == 1, result.stdout + result.stderr
    status, verdict = result.stdout.splitlines()
    assert f"Report {REPORT_ID!r}" in status
    assert expected in status
    assert verdict == "VERDICT FAIL (whole-report verification, 0/1 reports passed)"


def test_reports_every_input_after_failure(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")

    result = run_verifier(invalid, EXPORT)

    assert result.returncode == 1, result.stdout + result.stderr
    failure, success, verdict = result.stdout.splitlines()
    assert str(invalid) in failure
    assert f"Report {REPORT_ID!r}" in success
    assert verdict == "VERDICT FAIL (whole-report verification, 1/2 reports passed)"
