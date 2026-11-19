"""The Pages demo's Twilio-ingest story: baked artifacts and their shape."""

import json
from pathlib import Path

from scripts.export_demo import TWILIO_DEMO_ID, export
from subpoena.models import AuditReport, ClaimSource, VerdictStatus


def _baked(tmp_path: Path) -> tuple[Path, AuditReport]:
    out = tmp_path / "data"
    export(out)
    report = AuditReport.model_validate_json((out / f"run-{TWILIO_DEMO_ID}.json").read_bytes())
    return out, report


def test_index_lists_the_twilio_story(tmp_path):
    out, _ = _baked(tmp_path)
    index = json.loads((out / "scenarios.json").read_text())
    (entry,) = [item for item in index if item["group"] == "twilio"]
    assert entry["id"] == TWILIO_DEMO_ID
    assert entry["known_gap"] is False
    assert (out / f"audit-aud-{TWILIO_DEMO_ID}.json").exists()
    assert (out / f"report-aud-{TWILIO_DEMO_ID}.md").exists()


def test_report_is_the_hamming_story(tmp_path):
    _, report = _baked(tmp_path)
    assert report.call.transcript == ()
    assert report.call.raw_transcript.startswith("You're all set for Tuesday")
    assert report.call.provenance is not None
    assert report.call.provenance.platform == "twilio"
    assert report.call.provenance.completion_callback_at is not None
    by_type = {verdict.claim.type: verdict for verdict in report.verdicts}
    assert by_type["ConfirmationSent"].status == VerdictStatus.VERIFIED
    assert by_type["AppointmentBooked"].status == VerdictStatus.NOT_FOUND
    assert all(v.claim.source == ClaimSource.STRUCTURED for v in report.verdicts)
    # Both claims carry tool-log turn indexes with no timed transcript turn, so
    # the demo page renders them from its unturned-claims branch.
    assert report.call.transcript == ()
    assert report.seal is not None
    assert report.seal.chain_hash


def test_baked_bytes_are_deterministic(tmp_path):
    first, _ = _baked(tmp_path / "one")
    second, _ = _baked(tmp_path / "two")
    assert (first / f"run-{TWILIO_DEMO_ID}.json").read_bytes() == (
        second / f"run-{TWILIO_DEMO_ID}.json"
    ).read_bytes()
