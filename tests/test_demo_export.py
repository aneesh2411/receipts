"""The GitHub Pages demo is baked from the same code that runs the live API."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from subpoena.scenarios import BY_ID

SPEC = importlib.util.spec_from_file_location(
    "export_demo", Path(__file__).parent.parent / "scripts" / "export_demo.py"
)
export_demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_demo)


def test_every_scenario_is_baked_with_its_report_and_markdown(tmp_path):
    files = export_demo.export(tmp_path)
    assert len(files) == 3 * len(BY_ID) + 1
    index = json.loads((tmp_path / "scenarios.json").read_text())
    assert {s["id"] for s in index} == set(BY_ID)
    for scenario_id in ("clean-book", "fault-wrong-time", "edge-same-name-patients"):
        report = json.loads((tmp_path / f"run-{scenario_id}.json").read_text())
        assert report["verdicts"] and report["call"]["transcript"]
        assert report["seal"]["signature"]
        md = (tmp_path / f"report-{report['audit_id']}.md").read_text()
        assert report["outcome"] in md or "RECEIPT" in md


def test_export_is_deterministic(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    export_demo.export(first)
    export_demo.export(second)
    assert (first / "run-fault-wrong-time.json").read_bytes() == (
        second / "run-fault-wrong-time.json"
    ).read_bytes()
