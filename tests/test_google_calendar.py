"""The Google Calendar adapter: mapping, before-images, sync tokens, actor."""

from __future__ import annotations

from datetime import timedelta

import pytest

from receipts.models import AppointmentStatus, Entity
from receipts.scenarios.world import CALL_START, PATEL, KIM, at
from receipts.sor.base import RecordNotFound
from receipts.sor.google_calendar import (
    GoogleCalendarAdapter,
    GoogleCalendarReader,
    SnapshotCache,
)

from fake_gcal import FakeCalendarService

CALENDARS = {PATEL: "cal-patel", KIM: "cal-kim"}
START = at(2, 14, 0)


def _adapter(actor="receptionist-agent", clock=lambda: CALL_START):
    service = FakeCalendarService(clock)
    return GoogleCalendarAdapter(
        service, CALENDARS, actor=actor, clock=clock, cache=SnapshotCache()
    )


def test_create_then_get_and_list_roundtrip():
    adapter = _adapter()
    apt = adapter.create_appointment(
        patient_id="pat_0001", provider=PATEL, start=START, duration_min=45, reason="cleaning"
    )
    assert apt.provider == PATEL and apt.duration_min == 45 and apt.reason == "cleaning"
    assert adapter.get_appointment(apt.id) == apt
    assert adapter.list_appointments(patient_id="pat_0001") == [apt]
    assert adapter.list_appointments(provider=KIM) == []
    in_window = adapter.list_appointments(window=(START - timedelta(hours=1), START + timedelta(hours=2)))
    assert in_window == [apt]


def test_cancel_maps_to_cancelled_status_and_is_hidden_by_default():
    adapter = _adapter()
    apt = adapter.create_appointment(patient_id="pat_0001", provider=PATEL, start=START)
    cancelled = adapter.cancel_appointment(apt.id)
    assert cancelled.status == AppointmentStatus.CANCELLED
    assert adapter.list_appointments() == []
    assert adapter.list_appointments(include_cancelled=True)[0].status == (
        AppointmentStatus.CANCELLED
    )


def test_reschedule_and_update_move_fields_and_stamp_actor():
    adapter = _adapter()
    apt = adapter.create_appointment(patient_id="pat_0001", provider=PATEL, start=START)
    moved = adapter.reschedule_appointment(apt.id, START + timedelta(days=1))
    assert moved.start == START + timedelta(days=1) and moved.duration_min == 30
    changed = adapter.update_appointment(
        apt.id, patient_id="pat_0009", duration_min=60, reason="filling"
    )
    assert changed.patient_id == "pat_0009" and changed.duration_min == 60
    assert changed.reason == "filling"
    moved_cal = adapter.update_appointment(apt.id, provider=KIM)
    assert moved_cal.provider == KIM
    assert adapter.get_appointment(apt.id).provider == KIM


def test_delete_removes_the_appointment():
    adapter = _adapter()
    apt = adapter.create_appointment(patient_id="pat_0001", provider=PATEL, start=START)
    adapter.delete_appointment(apt.id)
    # Like the real API, a deleted event is only visible as cancelled.
    assert adapter.list_appointments() == []
    with pytest.raises(RecordNotFound):
        adapter.reschedule_appointment(apt.id, START)


def test_changes_carry_before_images_from_the_snapshot_cache():
    clock_time = {"t": CALL_START}

    def clock():
        return clock_time["t"]

    adapter = _adapter(clock=clock)
    apt = adapter.create_appointment(patient_id="pat_0001", provider=PATEL, start=START)

    reader = GoogleCalendarReader(adapter._service, CALENDARS, cache=SnapshotCache())
    reader.sync()  # snapshot the world as it stood before the window
    clock_time["t"] = CALL_START + timedelta(minutes=3)
    adapter.reschedule_appointment(apt.id, START + timedelta(hours=1))

    changes = reader.changes(CALL_START, CALL_START + timedelta(minutes=5))
    assert len(changes) == 1
    (change,) = changes
    assert change.entity is Entity.APPOINTMENT and change.op == "update"
    assert change.before["start"] != change.after["start"]
    assert change.actor == "receptionist-agent"


def test_changes_without_a_snapshot_read_as_inserts():
    adapter = _adapter()
    adapter.create_appointment(patient_id="pat_0001", provider=PATEL, start=START)
    reader = GoogleCalendarReader(adapter._service, CALENDARS, cache=SnapshotCache())
    changes = reader.changes(CALL_START - timedelta(minutes=1), CALL_START + timedelta(minutes=1))
    assert [c.op for c in changes] == ["insert"]
    assert changes[0].before is None


def test_sync_is_incremental_via_sync_tokens(tmp_path):
    clock_time = {"t": CALL_START}
    adapter = _adapter(clock=lambda: clock_time["t"])
    cache = SnapshotCache.load(tmp_path / "snapshots.json")
    reader = GoogleCalendarReader(adapter._service, CALENDARS, cache=cache)
    reader.sync()
    assert cache.sync_tokens  # a token per calendar was stored
    first = adapter.create_appointment(patient_id="pat_0001", provider=PATEL, start=START)
    clock_time["t"] = CALL_START + timedelta(minutes=1)
    reader.sync()
    assert first.id in reader._cache.events
    # The cache survives a reload: before-images persist across restarts.
    reloaded = SnapshotCache.load(tmp_path / "snapshots.json")
    assert first.id in reloaded.events


def test_change_feed_survives_cache_reload(tmp_path):
    clock_time = {"t": CALL_START}
    adapter = _adapter(clock=lambda: clock_time["t"])
    cache = SnapshotCache.load(tmp_path / "snapshots.json")
    reader = GoogleCalendarReader(adapter._service, CALENDARS, cache=cache)
    apt = adapter.create_appointment(patient_id="pat_0001", provider=PATEL, start=START)
    reader.sync()
    # Restart: a fresh reader over the persisted cache still has before-images.
    reader2 = GoogleCalendarReader(
        adapter._service, CALENDARS, cache=SnapshotCache.load(tmp_path / "snapshots.json")
    )
    clock_time["t"] = CALL_START + timedelta(minutes=2)
    adapter.cancel_appointment(apt.id)
    (change,) = reader2.changes(CALL_START, CALL_START + timedelta(minutes=5))
    assert change.op == "update"
    assert change.before["status"] == "booked"
    assert change.after["status"] == "cancelled"
