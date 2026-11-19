"""The audit diff is generated from two sealed replays of the same golden call."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from subpoena.auditor import RuleBasedExtractor, Sealer
from subpoena.scenarios.golden import BY_ID
from subpoena.scenarios.world import run_scenario

ROOT = Path(__file__).resolve().parents[1]
SEALING_KEY = b"subpoena-pages-demo"


def test_export_matches_sealed_replays(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "scripts/export_diff_demo.py", "--out", str(tmp_path)],
        cwd=ROOT,
        check=True,
    )

    relative_data = "data-diff/diff.json"
    diff = json.loads((tmp_path / relative_data).read_text(encoding="utf-8"))
    page = (tmp_path / "audit-diff.html").read_text(encoding="utf-8")
    assert f'fetch("{relative_data}")' in page

    assert diff["scenario_id"] == "fault-wrong-time"
    fault = BY_ID[diff["scenario_id"]]
    paths = {side: tmp_path / "data-diff" / f"{side}.json" for side in ("before", "after")}
    sealer = Sealer(SEALING_KEY)
    verdicts = {}
    for side, scenario in (("before", fault), ("after", replace(fault, faults={}))):
        report = run_scenario(scenario, extractor=RuleBasedExtractor(), sealer=sealer).report
        saved = json.loads(paths[side].read_text(encoding="utf-8"))
        assert saved == report.model_dump(mode="json")
        assert report.call.call_id == diff["call_id"]
        assert report.outcome.value == diff["runs"][side]["outcome"]
        verdicts[side] = {verdict.claim.claim_id: verdict for verdict in report.verdicts}

    (booking, confirmation) = diff["claims"]
    assert {row["claim_id"] for row in diff["claims"]} == verdicts["before"].keys()
    assert verdicts["before"].keys() == verdicts["after"].keys()
    for row in diff["claims"]:
        for side in ("before", "after"):
            verdict = verdicts[side][row["claim_id"]]
            assert row[side] == verdict.status.value
            assert row["claim_type"] == type(verdict.claim).__name__

    assert (booking["before"], booking["after"]) == ("MISMATCH", "VERIFIED")
    assert (confirmation["before"], confirmation["after"]) == ("VERIFIED", "VERIFIED")
    assert confirmation["fields"] == []
    (change,) = booking["fields"]
    assert (change["kind"], change["field"]) == ("receipt", "start")
    for side in ("before", "after"):
        source = verdicts[side][booking["claim_id"]]
        assert change[side] == [
            row.model_dump(mode="json", exclude={"field"})
            for row in source.diffs
            if row.field == "start"
        ]

    cli = subprocess.run(
        [
            sys.executable,
            "scripts/diff_audits.py",
            str(paths["before"]),
            str(paths["after"]),
            "--key",
            SEALING_KEY.decode(),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert cli.stdout.splitlines() == [
        f"Before seal: {diff['runs']['before']['seal']}",
        f"After seal: {diff['runs']['after']['seal']}",
        *diff["cli_diff"],
    ]

    for output in (
        relative_data,
        "audit-diff.html",
        "data-diff/before.json",
        "data-diff/after.json",
    ):
        assert (tmp_path / output).read_bytes() == (ROOT / "docs" / "demo" / output).read_bytes()
