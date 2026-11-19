"""Every fault mode is caught, and caught for the right reason.

`test_golden.py` checks statuses against the labels. These tests go further for
each fault: the specific field, severity and evidence the auditor reports.
"""

from __future__ import annotations

import pytest

from subpoena.models import FindingKind, Severity, VerdictStatus
from subpoena.scenarios import BY_ID, GOLDEN, run_scenario
from subpoena.suspect import REQUIRED_FAULTS, FaultMode

V, MM, NF = VerdictStatus.VERIFIED, VerdictStatus.MISMATCH, VerdictStatus.NOT_FOUND


def _report(scenario_id: str):
    return run_scenario(BY_ID[scenario_id]).report


def _wrong_fields(verdict) -> set[str]:
    return {d.field for d in verdict.diffs if not d.match}


def test_every_fault_mode_has_a_golden_scenario():
    covered = {mode for s in GOLDEN for mode in s.fault_modes}
    assert covered == set(FaultMode)
    assert REQUIRED_FAULTS <= covered


# ------------------------- the six faults from the brief ------------------- #


def test_phantom_booking():
    booked, confirmation = _report("fault-phantom-booking").verdicts
    assert (booked.status, booked.severity) == (NF, Severity.CRITICAL)
    assert booked.checks[0].passed is False
    assert booked.evidence[0].source == "journal"
    assert confirmation.status is V  # the text really was sent, which makes it worse


def test_wrong_time():
    booked, _ = _report("fault-wrong-time").verdicts
    assert (booked.status, booked.severity) == (MM, Severity.CRITICAL)
    assert _wrong_fields(booked) == {"start"}
    (diff,) = [d for d in booked.diffs if d.field == "start"]
    assert "2:30 PM" in diff.claimed and "3:30 PM" in diff.actual
    assert [c.passed for c in booked.checks][:2] == [True, False]


def test_unclaimed_write():
    report = _report("fault-unclaimed-write")
    assert [v.status for v in report.verdicts] == [V, V]
    (finding,) = report.findings
    assert (finding.kind, finding.code) == (
        FindingKind.UNCLAIMED_WRITE,
        "unclaimed_appointment_created",
    )
    assert finding.evidence[0].record["reason"] == "follow-up"


def test_phantom_confirmation():
    booked, confirmation = _report("fault-phantom-confirmation").verdicts
    assert booked.status is V
    assert (confirmation.status, confirmation.severity) == (NF, Severity.MEDIUM)


def test_phantom_handoff():
    (handoff,) = _report("fault-phantom-handoff").verdicts
    assert (handoff.status, handoff.severity) == (NF, Severity.HIGH)
    assert "call this person back" in handoff.summary


def test_double_book():
    report = _report("fault-double-book")
    assert [v.status for v in report.verdicts] == [V, V]  # the claim itself is true
    (finding,) = report.findings
    assert (finding.kind, finding.code) == (FindingKind.POLICY_VIOLATION, "double_booking")
    assert len({e.ref for e in finding.evidence}) == 2  # both colliding appointments cited


# ------------------------------ extended faults ---------------------------- #


def test_wrong_patient():
    booked, _ = _report("fault-wrong-patient").verdicts
    assert booked.status is MM and _wrong_fields(booked) == {"patient"}
    assert booked.severity is Severity.CRITICAL


def test_duplicate_write_is_both_unclaimed_and_a_double_booking():
    report = _report("fault-duplicate-write")
    assert sorted(f.code for f in report.findings) == [
        "double_booking",
        "unclaimed_appointment_created",
    ]


def test_rollback_is_reported_as_written_then_removed():
    booked, _ = _report("fault-rollback").verdicts
    assert booked.status is NF
    assert "then removed" in booked.summary
    assert any("net: transient" in e.note for e in booked.evidence)


def test_off_hours_booking():
    (finding,) = _report("fault-off-hours").findings
    assert finding.code == "outside_business_hours"


def test_silent_crm_edit():
    report = _report("fault-silent-crm-edit")
    (finding,) = report.findings
    assert (finding.code, finding.severity) == ("unclaimed_patient_modified", Severity.HIGH)
    assert [v.status for v in report.verdicts] == [V, V]  # patient still resolves by name


def test_wrong_recipient():
    _, confirmation = _report("fault-wrong-recipient").verdicts
    assert confirmation.status is MM and _wrong_fields(confirmation) == {"recipient"}
    assert confirmation.severity is Severity.HIGH


def test_stale_confirmation():
    _, confirmation = _report("fault-stale-confirmation").verdicts
    assert confirmation.status is MM and _wrong_fields(confirmation) == {"stated_time"}


def test_zombie_reschedule_fails_the_side_effect_check():
    (moved,) = _report("fault-zombie-reschedule").verdicts
    assert moved.status is MM and _wrong_fields(moved) == {"old_slot_released"}
    side_effects = next(c for c in moved.checks if c.name.value == "side_effects")
    assert side_effects.passed is False


def test_lost_reschedule_is_critical():
    (moved,) = _report("fault-lost-reschedule").verdicts
    assert (moved.status, moved.severity) == (MM, Severity.CRITICAL)
    assert _wrong_fields(moved) == {"new_appointment"}


def test_reschedule_to_the_wrong_time():
    (moved,) = _report("fault-reschedule-wrong-time").verdicts
    assert moved.status is MM and _wrong_fields(moved) == {"new_start"}


def test_phantom_reschedule_cites_the_untouched_original():
    (moved,) = _report("fault-phantom-reschedule").verdicts
    assert moved.status is NF
    assert any("untouched" in e.note for e in moved.evidence)


def test_phantom_cancel_cites_the_still_booked_appointment():
    (cancelled,) = _report("fault-phantom-cancel").verdicts
    assert (cancelled.status, cancelled.severity) == (NF, Severity.MEDIUM)
    assert "still on the books" in cancelled.summary


def test_wrong_appointment_cancelled():
    (cancelled,) = _report("fault-cancel-wrong-appointment").verdicts
    assert (cancelled.status, cancelled.severity) == (MM, Severity.CRITICAL)


def test_downgraded_handoff():
    (handoff,) = _report("fault-downgraded-handoff").verdicts
    assert handoff.status is MM and _wrong_fields(handoff) == {"priority"}


def test_spoken_only_promises_are_recovered_from_the_transcript():
    report = _report("fault-spoken-only-with-confirmation")
    assert report.call.claims == ()  # the agent logged nothing
    assert [(v.claim.type, v.claim.source.value, v.status) for v in report.verdicts] == [
        ("AppointmentBooked", "transcript", NF),
        ("ConfirmationSent", "transcript", NF),
    ]


def test_misspoken_time_verifies_the_log_and_flags_what_the_caller_heard():
    logged, confirmation, spoken, spoken_confirmation = _report("fault-misspoken-time").verdicts
    assert (logged.claim.source.value, logged.status) == ("structured", V)
    assert (confirmation.claim.source.value, confirmation.status) == ("structured", V)
    assert (spoken.claim.source.value, spoken.status) == ("transcript", NF)
    assert (spoken_confirmation.claim.source.value, spoken_confirmation.status) == (
        "transcript",
        NF,
    )
    assert confirmation.claim.about_start == logged.claim.start
    assert spoken_confirmation.claim.about_start == spoken.claim.start
    assert spoken.claim.start != logged.claim.start


@pytest.mark.parametrize("scenario", [s for s in GOLDEN if s.fault_modes and not s.known_gap],
                         ids=lambda s: s.id)  # fmt: skip
def test_every_faulty_call_is_flagged_and_every_flag_has_evidence(scenario):
    report = run_scenario(scenario).report
    assert report.outcome.value == "DISCREPANCIES"
    for verdict in report.verdicts:
        if verdict.status in (MM, NF):
            assert verdict.evidence and verdict.remediation and verdict.summary
    for finding in report.findings:
        assert finding.evidence and finding.remediation
