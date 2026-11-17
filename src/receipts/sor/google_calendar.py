"""Where a real Google Calendar adapter plugs in.

This is a deliberately unimplemented skeleton: it documents the mapping so the
adapter can be written without touching the auditor.

Mapping
-------
``list_appointments``  -> ``events.list(calendarId, timeMin, timeMax, singleEvents=True)``
``get_appointment``    -> ``events.get(calendarId, eventId)``
``changes(since, until)`` -> ``events.list(calendarId, updatedMin=since, showDeleted=True)``
                            filtered to ``updated <= until``.

Two things Google Calendar does not hand you, which the adapter must supply:

1. **Before-images.** The API returns the current event, not the previous
   version. Keep a snapshot cache keyed by ``eventId`` (refreshed with
   ``syncToken`` incremental sync) and emit ``Change(before=cached, after=current)``.
2. **Actor.** Use ``event.creator`` / the service account the agent writes with,
   so the auditor can attribute writes to the agent rather than front-desk staff.

A cancelled event (``status == "cancelled"``) maps to ``AppointmentStatus.CANCELLED``.
Provider maps to the calendar (one calendar per provider) and patient identity to
an extended property written by the booking integration.
"""

from __future__ import annotations

from datetime import datetime

from receipts.models import Appointment, Change


class GoogleCalendarReader:
    """Implements ``CalendarReader`` against the Google Calendar API (not yet built)."""

    def __init__(self, calendar_ids_by_provider: dict[str, str]) -> None:
        self._calendars = dict(calendar_ids_by_provider)

    def get_appointment(self, appointment_id: str) -> Appointment | None:
        raise NotImplementedError("see module docstring for the events.get mapping")

    def list_appointments(
        self,
        *,
        patient_id: str | None = None,
        provider: str | None = None,
        window: tuple[datetime, datetime] | None = None,
        include_cancelled: bool = False,
    ) -> list[Appointment]:
        raise NotImplementedError("see module docstring for the events.list mapping")

    def changes(self, since: datetime, until: datetime) -> list[Change]:
        raise NotImplementedError("see module docstring for the updatedMin mapping")
