"""The standalone review demo is reproducible and shows real grouping ambiguities."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_review_export_is_reproducible(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    for out in (first, second):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/export_review_demo.py"), "--out", str(out)],
            cwd=ROOT,
            check=True,
        )

    relative_data = "data-review/review.json"
    for relative_path in ("review.html", relative_data):
        expected = (ROOT / "docs/demo" / relative_path).read_bytes()
        assert (first / relative_path).read_bytes() == expected
        assert (second / relative_path).read_bytes() == expected

    page = (first / "review.html").read_text(encoding="utf-8")
    assert f'fetch("{relative_data}")' in page
    for text in (
        "merges the auditor refused to make on its own",
        "Call timeline",
        "Call outcome",
        "UNMERGED · Pending a human decision",
    ):
        assert text in page

    shared_phone, missing_phone, topic = json.loads((first / relative_data).read_bytes())["reviews"]
    assert [review["reason"] for review in (shared_phone, missing_phone, topic)] == [
        "same-phone-different-names",
        "same-name-no-phone",
        "ambiguous-handoff-topic",
    ]
    assert "Phone +15550101001 appears as maya chen, mina chen." in shared_phone["detail"]
    assert "Maya Chen appears without a verified number" in missing_phone["detail"]
    assert "partly overlaps another request from this caller" in topic["detail"]

    for review, case, second_outcome in (
        (shared_phone, "shared-phone", "CLEAN"),
        (missing_phone, "missing-phone", "CLEAN"),
        (topic, "topic", "DISCREPANCIES"),
    ):
        assert review["audits"] == [f"aud-review-{case}-1", f"aud-review-{case}-2"]
        assert [call["audit_id"] for call in review["calls"]] == review["audits"]
        assert [call["started_at"] for call in review["calls"]] == [
            "2026-03-02T09:05:00-05:00",
            "2026-03-03T09:05:00-05:00",
        ]
        assert [call["outcome"] for call in review["calls"]] == ["CLEAN", second_outcome]
