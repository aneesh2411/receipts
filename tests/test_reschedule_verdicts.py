"""Regression: reschedule claims that used to earn a false VERIFIED.

From docs/FAILURE_ANALYSIS.md section 4, items 2 and 3: an in-place move that
also rewrites the patient, provider or duration verified, and so did a
"reschedule" of an appointment that never existed.
"""

from __future__ import annotations

from datetime import timedelta

from receipts.models import Rescheduled
from receipts.scenarios.world import CALL_START, MAYA, PATEL, at


def _seed(clinic):
    """A writer from before the call, so seeds are not the agent's writes."""
    return clinic.as_actor("seed", CALL_START - timedelta(days=1))


def _reschedule_claim(**kw) -> Rescheduled:
    return Rescheduled(
        claim_id="c1",
        turn_index=0,
        patient=MAYA,
        old_start=at(1, 10),
        new_start=at(3, 11),
        provider=PATEL,
        **kw,
    )


def _seed_appointment(clinic) -> str:
    patient = clinic.patient(MAYA)
    return (
        _seed(clinic)
        .calendar.create_appointment(
            patient_id=patient.id, provider=PATEL, start=at(1, 10), duration_min=30
        )
        .id
    )


def test_in_place_move_that_rewrites_the_record_is_a_mismatch(clinic) -> None:
    appt_id = _seed_appointment(clinic)
    clinic.agent.calendar.reschedule_appointment(appt_id, at(3, 11))
    clinic.agent.calendar.update_appointment(appt_id, provider="Dr. Kim", duration_min=60)

    report = clinic.audit(clinic.call(claims=[_reschedule_claim()]))
    (verdict,) = report.verdicts
    assert verdict.status.value == "MISMATCH"
    rewritten = {d.field for d in verdict.diffs if not d.match}
    assert "rewrite_provider" in rewritten and "rewrite_duration" in rewritten


def test_honest_in_place_move_still_verifies(clinic) -> None:
    appt_id = _seed_appointment(clinic)
    clinic.agent.calendar.reschedule_appointment(appt_id, at(3, 11))

    report = clinic.audit(clinic.call(claims=[_reschedule_claim()]))
    (verdict,) = report.verdicts
    assert verdict.status.value == "VERIFIED"


def test_move_of_a_visit_that_never_existed_is_a_mismatch(clinic) -> None:
    patient = clinic.patient(MAYA)
    clinic.agent.calendar.create_appointment(
        patient_id=patient.id, provider=PATEL, start=at(3, 11), duration_min=30
    )

    report = clinic.audit(clinic.call(claims=[_reschedule_claim()]))
    (verdict,) = report.verdicts
    assert verdict.status.value == "MISMATCH"
    missing = [d for d in verdict.diffs if d.field == "old_appointment"]
    assert missing and not missing[0].match


def test_move_with_old_slot_released_verifies_via_recreate(clinic) -> None:
    appt_id = _seed_appointment(clinic)
    before = clinic.agent.calendar.get_appointment(appt_id)
    clinic.agent.calendar.cancel_appointment(appt_id)
    clinic.agent.calendar.create_appointment(
        patient_id=before.patient_id,
        provider=before.provider,
        start=at(3, 11),
        duration_min=before.duration_min,
        reason=before.reason,
    )

    report = clinic.audit(clinic.call(claims=[_reschedule_claim()]))
    (verdict,) = report.verdicts
    assert verdict.status.value == "VERIFIED"


def test_call_window_is_sane() -> None:
    assert CALL_START < at(1, 10)
