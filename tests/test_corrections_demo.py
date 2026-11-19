"""Verify the correction-binding walkthrough and its committed Pages artifact."""

import json
import re

import pytest

from scripts.export_corrections_demo import DEFAULT_OUT, SEALING_KEY, export
from subpoena.auditor import Sealer
from subpoena.models import Appointment, AppointmentBooked, AuditReport, ClaimSource
from subpoena.scenarios.world import at


def test_corrections_export_matches_pages(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    export(first)
    export(second)

    page = (DEFAULT_OUT.parent / "corrections.html").read_text(encoding="utf-8")
    assert re.findall(r'fetch\("data-corrections/([^"]+)"\)', page) == ["cases.json"]
    assert (first / "cases.json").read_bytes() == (second / "cases.json").read_bytes()
    assert (first / "cases.json").read_bytes() == (DEFAULT_OUT / "cases.json").read_bytes()


@pytest.mark.parametrize(
    ("case_index", "status", "outcome", "booked_day"),
    [
        (0, "VERIFIED", "CLEAN", 1),
        (1, "MISMATCH", "DISCREPANCIES", 2),
    ],
)
def test_corrections_bind_the_acknowledgment_and_check_the_write(
    tmp_path, case_index, status, outcome, booked_day
):
    export(tmp_path)
    cases = json.loads((tmp_path / "cases.json").read_bytes())
    assert len(cases) == 2
    case = cases[case_index]
    report = AuditReport.model_validate(case["audit"])
    acknowledgment = AppointmentBooked.model_validate(case["acknowledgment"])
    (verdict,) = report.verdicts
    assert report.outcome == outcome
    assert verdict.status == status
    assert isinstance(verdict.claim, AppointmentBooked)
    assert verdict.claim.corrects_prior and acknowledgment.corrects_prior
    assert acknowledgment.source is ClaimSource.TRANSCRIPT
    assert verdict.claim.start == acknowledgment.start == at(1, 14, 30)

    turns = report.call.transcript
    corrected = turns[acknowledgment.turn_index - 1]
    spoken = turns[acknowledgment.turn_index]
    assert corrected.speaker == "caller"
    assert "Actually, could we make that Tuesday" in corrected.text
    assert spoken.speaker == "agent"
    assert acknowledgment.utterance in spoken.text
    assert any(
        "earlier AppointmentBooked claim is withdrawn" in entry.message for entry in report.trail
    )

    (evidence,) = verdict.evidence
    assert evidence.source == "calendar"
    booking = Appointment.model_validate(evidence.record)
    assert booking.id == evidence.ref
    assert booking.status == "booked"
    assert booking.start == at(booked_day, 14, 30)
    assert evidence.ref in verdict.summary
    if booked_day == 2:
        original = report.call.claims[0]
        assert isinstance(original, AppointmentBooked)
        assert booking.start == original.start
        assert "Wed Mar 4 2026, 2:30 PM EST" in verdict.summary
        assert "exact value the caller corrected away from" in verdict.summary
    assert Sealer(SEALING_KEY).verify(report, strict=True).ok
