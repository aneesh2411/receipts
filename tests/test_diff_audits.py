import json
import subprocess
import sys
from pathlib import Path

import pytest

from subpoena.auditor.seal import Sealer
from subpoena.models import AuditReport

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diff_audits.py"
EXPORT = ROOT / "docs" / "demo" / "data" / "audit-aud-clean-family-two-bookings.json"
DEMO_KEY = "subpoena-pages-demo"


@pytest.fixture
def variant(tmp_path):
    payload = json.loads(EXPORT.read_text(encoding="utf-8"))
    path = tmp_path / "after.json"

    def write(*, reseal=True):
        if reseal:
            report = AuditReport.model_validate(payload)
            sealed = Sealer(DEMO_KEY.encode()).seal(report).model_dump(mode="json")
        else:
            sealed = payload
        path.write_text(json.dumps(sealed), encoding="utf-8")
        return path

    return payload, write


def run_diff(before, after, *, key=None):
    command = [sys.executable, str(SCRIPT), str(before), str(after)]
    if key is not None:
        command.extend(["--key", key])
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)


def test_identical_audits():
    result = run_diff(EXPORT, EXPORT)
    assert result.returncode == 0, result.stderr
    before, after, changes = result.stdout.splitlines()
    assert before.startswith("Before seal: OK integrity=intact authentication=unverifiable")
    assert after.startswith("After seal: OK integrity=intact authentication=unverifiable")
    assert changes == "No claim changes."
    assert result.stderr == ""


def test_verdict_flip(variant):
    payload, write = variant
    verdict = payload["verdicts"][0]
    verdict["status"] = "MISMATCH"
    result = run_diff(write(), EXPORT, key=DEMO_KEY)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("authentication=authenticated") == 2
    assert (
        f'Claim "{verdict["claim"]["claim_id"]}":\n  Verdict: MISMATCH -> VERIFIED' in result.stdout
    )


def test_added_and_removed_claims_are_not_paired(variant):
    payload, write = variant
    claim = payload["verdicts"][0]["claim"]
    original_id = claim["claim_id"]
    claim["claim_id"] = "a-new-claim"
    after = write()

    result = run_diff(EXPORT, after)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[2:] == [
        'ADDED Claim "a-new-claim" (VERIFIED)',
        f'REMOVED Claim "{original_id}" (VERIFIED)',
    ]


def test_changed_field_values(variant):
    payload, write = variant
    verdict = payload["verdicts"][0]
    verdict["claim"]["reason"] = "follow-up"
    provider = next(row for row in verdict["diffs"] if row["field"] == "provider")
    provider.update(actual="Dr. Shah", match=False)

    result = run_diff(EXPORT, write())
    assert result.returncode == 0, result.stderr
    assert 'Claim field "reason": "cleaning" -> "follow-up"' in result.stdout
    assert (
        'Receipt field "provider": [{"actual":"Dr. Kim","claimed":"Dr. Kim","match":true}]'
        ' -> [{"actual":"Dr. Shah","claimed":"Dr. Kim","match":false}]'
    ) in result.stdout
    assert "Verdict:" not in result.stdout

    payload["verdicts"].reverse()
    verdict["diffs"].reverse()
    assert run_diff(EXPORT, write()).stdout == result.stdout


@pytest.mark.parametrize("tamper", ["edit verdict", "drop default field"])
@pytest.mark.parametrize("tampered_first", [True, False])
def test_tampered_input_refuses_diff(variant, tamper, tampered_first):
    payload, write = variant
    if tamper == "edit verdict":
        payload["verdicts"][0]["status"] = "MISMATCH"
    else:
        del payload["extraction"]["detail"]
    tampered = write(reseal=False)
    before, after = (tampered, EXPORT) if tampered_first else (EXPORT, tampered)
    failed, passed = ("Before", "After") if tampered_first else ("After", "Before")

    result = run_diff(before, after)
    assert result.returncode != 0
    assert result.stdout == ""
    assert f"{failed} seal: FAILED integrity=altered" in result.stderr
    assert f"{passed} seal: OK integrity=intact" in result.stderr
    assert "Diff refused" in result.stderr


def test_call_id_mismatch_still_diffs(variant):
    payload, write = variant
    original_id = payload["call"]["call_id"]
    payload["call"]["call_id"] = "reingested-call"
    payload["verdicts"][0]["status"] = "MISMATCH"

    result = run_diff(EXPORT, write())
    assert result.returncode == 0, result.stderr
    assert f"WARNING: CALL ID MISMATCH: {original_id} -> reingested-call" in result.stdout
    assert "Verdict: VERIFIED -> MISMATCH" in result.stdout
