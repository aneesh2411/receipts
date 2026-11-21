"""The demo's baked reports carry deterministic coverage gaps for the viewer."""

from __future__ import annotations

import json
from pathlib import Path

from test_demo_export import export_demo

DEMO_DATA = Path(__file__).resolve().parents[1] / "docs" / "demo" / "data"


def test_demo_coverage_gaps_are_baked_and_deterministic(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    export_demo.export(first)
    export_demo.export(second)

    for scenario, source in (
        ("edge-calendar-outage", "calendar"),
        ("edge-crm-outage", "crm"),
        ("edge-message-log-outage", "messages"),
    ):
        name = f"run-{scenario}.json"
        assert (first / name).read_bytes() == (second / name).read_bytes()
        report = json.loads((first / name).read_text())
        gaps = report["coverage_gaps"]
        assert any(
            gap["source"] == source
            and gap["kind"] == "unavailable"
            and gap["detail"]
            and gap["claim_ids"]
            for gap in gaps
        )
        for filename in (name, f"audit-{report['audit_id']}.json"):
            baked = json.loads((DEMO_DATA / filename).read_text())
            assert baked["coverage_gaps"] == gaps
