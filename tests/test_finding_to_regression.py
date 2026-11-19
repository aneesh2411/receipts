import json
import subprocess
import sys
from pathlib import Path

import pytest

from subpoena.auditor.seal import Sealer
from subpoena.evals import score_run
from subpoena.models import AuditReport
from subpoena.scenarios import GOLDEN, run_scenario

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "docs" / "demo" / "data" / "audit-aud-fault-double-book.json"
FINDING_ID = "call-fault-double-book-f1"


def run_generator(audit=EXPORT, finding_id=FINDING_ID, *args):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/finding_to_regression.py"),
            str(audit),
            finding_id,
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_skeleton(source):
    namespace = {}
    exec(compile(source, "<generated scenario>", "exec"), namespace)
    return namespace


def test_generates_deterministic_golden_scenario_from_published_export(tmp_path):
    payload = json.loads(EXPORT.read_text(encoding="utf-8"))
    output = tmp_path / "regression.py"

    stdout = run_generator()
    file_result = run_generator(EXPORT, FINDING_ID, "--output", str(output))
    assert stdout.returncode == file_result.returncode == 0
    assert stdout.stderr == file_result.stderr == file_result.stdout == ""
    assert output.read_bytes() == stdout.stdout.encode()
    assert payload["audit_id"] in stdout.stdout.splitlines()[1]
    assert payload["seal"]["content_hash"] in stdout.stdout.splitlines()[2]

    skeleton = load_skeleton(stdout.stdout)
    assert skeleton["CALL"] == payload["call"]
    assert skeleton["FINDING"] == payload["findings"][0]
    assert skeleton["VERDICTS"] == payload["verdicts"]

    original = next(scenario for scenario in GOLDEN if scenario.id == "fault-double-book")
    scenario = skeleton["build_scenario"](
        steps=original.steps,
        seed=original.seed,
        faults=original.faults,
    )
    report = run_scenario(scenario).report
    assert report.outcome.value == skeleton["EXPECTED_OUTCOME"]
    assert not score_run(
        scenario.id,
        scenario.expected_claims,
        scenario.expected_findings,
        report,
    ).problems


def test_partial_state_preserves_available_evidence_and_reports_missing_snapshots(tmp_path):
    payload = json.loads(EXPORT.read_text(encoding="utf-8"))
    finding = payload["findings"][0]
    missing_ref = finding["evidence"][1]["ref"]
    finding["evidence"][1]["record"] = None
    verdict = payload["verdicts"][1]
    verdict["evidence"] = []
    payload = Sealer().seal(AuditReport.model_validate(payload)).model_dump(mode="json")
    audit = tmp_path / "partial.json"
    audit.write_text(json.dumps(payload), encoding="utf-8")

    result = run_generator(audit)

    assert result.returncode == 0
    assert f"TODO: Finding {FINDING_ID!r} has no system-of-record snapshot" in result.stderr
    assert missing_ref in result.stderr
    assert f"TODO: Claim {verdict['claim']['claim_id']!r} has no" in result.stderr
    for message in result.stderr.splitlines():
        assert f"# {message}" in result.stdout
    skeleton = load_skeleton(result.stdout)
    assert skeleton["CALL"] == payload["call"]
    assert skeleton["FINDING"] == payload["findings"][0]
    assert skeleton["VERDICTS"] == payload["verdicts"]


def test_unknown_finding(tmp_path):
    output = tmp_path / "regression.py"
    result = run_generator(EXPORT, "unknown", "-o", str(output))
    assert result.returncode != 0
    assert "unknown finding id 'unknown'" in result.stderr
    assert not result.stdout
    assert not output.exists()


@pytest.mark.parametrize("edit", ["snapshot", "omitted default", "unsealed"])
def test_rejects_tampered_or_unsealed_audit(tmp_path, edit):
    payload = json.loads(EXPORT.read_text(encoding="utf-8"))
    if edit == "snapshot":
        payload["findings"][0]["evidence"][0]["record"]["provider"] = "Edited"
    elif edit == "omitted default":
        payload["findings"][0]["evidence"][0]["record"] = None
        payload = Sealer().seal(AuditReport.model_validate(payload)).model_dump(mode="json")
        del payload["findings"][0]["evidence"][0]["record"]
    else:
        payload["seal"] = None
    audit = tmp_path / "tampered.json"
    audit.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "regression.py"

    result = run_generator(audit, FINDING_ID, "-o", str(output))

    assert result.returncode != 0
    assert "audit seal verification failed" in result.stderr
    assert not result.stdout
    assert not output.exists()


def test_refuses_to_overwrite_existing_output(tmp_path):
    output = tmp_path / "golden.py"
    output.write_text("# original\n", encoding="utf-8")

    result = run_generator(EXPORT, FINDING_ID, "-o", str(output))

    assert result.returncode != 0
    assert "File exists" in result.stderr
    assert output.read_text(encoding="utf-8") == "# original\n"
