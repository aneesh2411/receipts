"""Exercise the offline SARIF export through its CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from subpoena.auditor.seal import Sealer
from subpoena.models import ConfirmationSent, Outcome, Severity, Verdict, VerdictStatus

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    (VerdictStatus.VERIFIED, Severity.INFO),
    (VerdictStatus.MISMATCH, Severity.CRITICAL),
    (VerdictStatus.NOT_FOUND, Severity.HIGH),
    (VerdictStatus.UNVERIFIABLE, Severity.MEDIUM),
    (VerdictStatus.MISMATCH, Severity.LOW),
    (VerdictStatus.NOT_FOUND, Severity.INFO),
)


@pytest.fixture
def report_path(clinic, tmp_path):
    claims = tuple(
        ConfirmationSent(claim_id=f"claim-{index}", turn_index=0, to="+14805550142")
        for index in range(len(CASES))
    )
    verdicts = tuple(
        Verdict(
            claim=claim,
            status=status,
            severity=severity,
            summary=f"Summary for {claim.claim_id}",
            remediation="Correct the record." if index == 1 else None,
        )
        for index, (claim, (status, severity)) in enumerate(zip(claims, CASES, strict=True))
    )
    report = clinic.audit(clinic.call(claims))
    stats = report.stats.model_copy(
        update={
            "verified": 1,
            "mismatch": 2,
            "not_found": 2,
            "unverifiable": 1,
            "max_severity": Severity.CRITICAL,
        }
    )
    report = report.model_copy(
        update={
            "outcome": Outcome.DISCREPANCIES,
            "verdicts": verdicts,
            "stats": stats,
        }
    )
    path = tmp_path / "report.json"
    path.write_text(Sealer().seal(report).model_dump_json(), encoding="utf-8")
    return path


def run_export(*args):
    return subprocess.run(
        [sys.executable, "scripts/report_to_sarif.py", *args],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )


def test_exports_non_verified_verdicts(report_path, tmp_path):
    first = run_export(report_path)
    assert first.returncode == 0, first.stderr
    sarif = json.loads(first.stdout)
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"]
    (run,) = sarif["runs"]
    results = run["results"]
    assert [(result["ruleId"], result["level"]) for result in results] == [
        ("subpoena/MISMATCH", "error"),
        ("subpoena/NOT_FOUND", "error"),
        ("subpoena/UNVERIFIABLE", "warning"),
        ("subpoena/MISMATCH", "note"),
        ("subpoena/NOT_FOUND", "note"),
    ]
    assert {rule["id"] for rule in run["tool"]["driver"]["rules"]} == {
        result["ruleId"] for result in results
    }
    assert (
        results[0]["message"]["text"] == "Summary for claim-1\n\nRemediation: Correct the record."
    )
    assert results[1]["message"]["text"] == "Summary for claim-2"
    assert len({r["partialFingerprints"]["subpoena/v1"] for r in results}) == len(results)

    second = run_export(report_path)
    assert second.returncode == 0, second.stderr
    assert second.stdout == first.stdout

    output = tmp_path / "report.sarif"
    file_export = run_export(report_path, "-o", output)
    assert file_export.returncode == 0, file_export.stderr
    assert file_export.stdout == b""
    assert output.read_bytes() == first.stdout


def test_verified_export_is_byte_identical(report_path):
    default = run_export(report_path)
    first = run_export(report_path, "--verify")
    second = run_export(report_path, "--verify")
    assert default.returncode == 0, default.stderr
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout == default.stdout


@pytest.mark.parametrize(
    ("original", "replacement", "reason"),
    [
        (b"Summary for claim-1", b"Summary for claim-X", b"report was altered"),
        (b',"remediation":null', b"", b"differs from the canonical report"),
    ],
)
def test_verified_export_rejects_altered_content(
    report_path, tmp_path, original, replacement, reason
):
    data = report_path.read_bytes()
    assert original in data
    report_path.write_bytes(data.replace(original, replacement, 1))
    output = tmp_path / "report.sarif"

    result = run_export(report_path, "--verify", "-o", output)
    assert result.returncode != 0
    assert result.stdout == b""
    assert str(report_path).encode() in result.stderr
    assert reason in result.stderr
    assert not output.exists()
    assert run_export(report_path).returncode == 0


def test_verified_export_rejects_unsealed_report(report_path):
    payload = json.loads(report_path.read_bytes())
    del payload["seal"]
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = run_export(report_path, "--verify")
    assert result.returncode != 0
    assert result.stdout == b""
    assert str(report_path).encode() in result.stderr
    assert b"report is not sealed" in result.stderr
    assert run_export(report_path).returncode == 0


@pytest.mark.parametrize("flags", [(), ("--verify",)])
@pytest.mark.parametrize(
    ("content", "error"),
    [
        (None, b"Unable to read report"),
        ("not JSON", b"Invalid audit report"),
        ("{}", b"Invalid audit report"),
    ],
)
def test_rejects_invalid_input(tmp_path, content, error, flags):
    path = tmp_path / "invalid.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    result = run_export(path, *flags)
    assert result.returncode != 0
    assert result.stdout == b""
    assert str(path).encode() in result.stderr
    assert error in result.stderr
