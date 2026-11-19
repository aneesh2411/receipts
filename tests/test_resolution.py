"""Verified resolution: closing needs two matching snapshots, never one assertion."""

from __future__ import annotations

from datetime import timedelta

from subpoena.auditor.resolution import Resolution, decide, take_snapshot
from subpoena.models import AppointmentBooked, Cancelled
from subpoena.scenarios.world import CALL_START, MAYA, PATEL, at

SLOT = at(1, 14, 30)
T0 = CALL_START + timedelta(hours=2)


def _booked() -> AppointmentBooked:
    return AppointmentBooked(claim_id="c1", turn_index=0, patient=MAYA, start=SLOT, provider=PATEL)


def _fix(clinic) -> None:
    clinic.as_actor("staff:fix", T0).calendar.create_appointment(
        patient_id=clinic.patient(MAYA).id, provider=PATEL, start=SLOT, duration_min=30
    )


def test_false_success_acknowledgement_never_closes(clinic) -> None:
    # The reviewer says "fixed"; the record never changed.
    sor = clinic.as_actor("auditor", T0)
    snaps = [
        take_snapshot(_booked(), sor, T0),
        take_snapshot(_booked(), sor, T0 + timedelta(minutes=10)),
    ]
    assert all(s.matches is False for s in snaps)
    assert decide(snaps) is Resolution.PENDING


def test_one_matching_snapshot_is_not_enough(clinic) -> None:
    _fix(clinic)
    snap = take_snapshot(_booked(), clinic.as_actor("auditor", T0), T0)
    assert snap.matches is True
    assert decide([snap]) is Resolution.PENDING


def test_two_matching_snapshots_apart_close_it(clinic) -> None:
    _fix(clinic)
    sor = clinic.as_actor("auditor", T0)
    snaps = [take_snapshot(_booked(), sor, T0 + timedelta(minutes=m)) for m in (0, 6)]
    assert decide(snaps) is Resolution.VERIFIED_CLOSED


def test_snapshots_too_close_together_stay_pending(clinic) -> None:
    _fix(clinic)
    sor = clinic.as_actor("auditor", T0)
    snaps = [take_snapshot(_booked(), sor, T0 + timedelta(minutes=m)) for m in (0, 1)]
    assert decide(snaps) is Resolution.PENDING


def test_delayed_write_pends_then_closes_on_later_rechecks(clinic) -> None:
    sor = clinic.as_actor("auditor", T0)
    early = take_snapshot(_booked(), sor, T0)
    assert decide([early]) is Resolution.PENDING
    _fix(clinic)  # the fix lands after the first recheck
    second = take_snapshot(_booked(), sor, T0 + timedelta(minutes=10))
    assert decide([early, second]) is Resolution.PENDING  # matched only once
    third = take_snapshot(_booked(), sor, T0 + timedelta(minutes=20))
    assert decide([early, second, third]) is Resolution.VERIFIED_CLOSED


def test_a_fix_that_is_rolled_back_reopens(clinic) -> None:
    _fix(clinic)
    sor = clinic.as_actor("auditor", T0)
    good = [take_snapshot(_booked(), sor, T0 + timedelta(minutes=m)) for m in (0, 6)]
    assert decide(good) is Resolution.VERIFIED_CLOSED
    appt = sor.calendar.list_appointments(patient_id=clinic.patient(MAYA).id)[0]
    clinic.as_actor("staff:undo", T0 + timedelta(minutes=8)).calendar.cancel_appointment(appt.id)
    bad = take_snapshot(_booked(), sor, T0 + timedelta(minutes=12))
    assert decide([*good, bad]) is Resolution.PENDING


def test_unreadable_source_is_inconclusive_never_closed(clinic) -> None:
    class Broken:
        @property
        def crm(self):
            raise ConnectionError("down")

    snap = take_snapshot(_booked(), Broken(), T0)
    assert snap.matches is None
    assert decide([snap, snap]) is Resolution.INCONCLUSIVE


def test_cancel_resolution_needs_the_slot_clear(clinic) -> None:
    _fix(clinic)
    claim = Cancelled(claim_id="c2", turn_index=0, patient=MAYA, start=SLOT)
    snap = take_snapshot(claim, clinic.as_actor("auditor", T0), T0)
    assert snap.matches is False
