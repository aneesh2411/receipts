"""The standalone incidents demo is reproducible and shows the billing saga."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_incidents_export_is_reproducible(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    for out in (first, second):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/export_incidents_demo.py"), "--out", str(out)],
            cwd=ROOT,
            check=True,
        )

    relative_data = "data-incidents/incidents.json"
    for relative_path in ("incidents.html", relative_data):
        expected = (ROOT / "docs/demo" / relative_path).read_bytes()
        assert (first / relative_path).read_bytes() == expected
        assert (second / relative_path).read_bytes() == expected

    page = (first / "incidents.html").read_text(encoding="utf-8")
    assert f'fetch("{relative_data}")' in page
    labels = ("Call timeline", "Repeated promises", "Duplicate ticket", "Fulfillment at saga end")
    for label in labels:
        assert label in page

    incident = json.loads((first / relative_data).read_bytes())
    assert incident["caller"] == "Maya Chen (+15550101001)"
    assert incident["request"] == "a callback about billing"
    assert incident["repeated_promises"] == 3
    assert incident["handoff_status"] == "fulfilled"

    calls = incident["calls"]
    assert [call["call_id"] for call in calls] == [
        "call-saga-callback-1",
        "call-saga-callback-2",
        "call-saga-callback-3",
    ]
    assert [call["outcome"] for call in calls] == ["CLEAN", "CLEAN", "DISCREPANCIES"]
    assert [[verdict["status"] for verdict in call["verdicts"]] for call in calls] == [
        ["VERIFIED"],
        ["VERIFIED"],
        ["NOT_FOUND"],
    ]

    (duplicate,) = incident["duplicate_writes"]
    assert duplicate["source"] == "tickets"
    assert duplicate["audit_id"] == calls[1]["audit_id"]
    assert duplicate["ref"] == "tkt_0002"
    assert "the first is tkt_0001" in duplicate["note"]
