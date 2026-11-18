"""Google Calendar as a system of record.

The auditor is typed against ``CalendarReader`` (see ``sor/base.py``); this module
maps that contract onto the Google Calendar API:

``list_appointments``  -> ``events.list(calendarId, timeMin, timeMax, singleEvents=True)``
``get_appointment``    -> ``events.get(calendarId, eventId)``
``changes(since, until)`` -> ``events.list(calendarId, updatedMin=since, showDeleted=True)``
                            filtered to ``updated <= until``.

Two things Google Calendar does not hand you, which this adapter supplies:

1. **Before-images.** The API returns the current event, not the previous version.
   ``SnapshotCache`` keeps the last-seen body of every event (refreshed with
   ``syncToken`` incremental sync) and ``changes`` emits
   ``Change(before=cached, after=current)``. Sync before the window you audit;
   a write the cache never saw has no before-image and reads as an insert.
2. **Actor.** The writer stamps ``extendedProperties.private.actor`` on every
   event it touches, so the auditor can attribute writes to the agent rather
   than front-desk staff. ``event.creator.email`` is the fallback.

A cancelled event (``status == "cancelled"``) maps to ``AppointmentStatus.CANCELLED``.
Provider maps to the calendar (one calendar per provider) and patient identity to
the ``patientId`` private extended property written by the booking integration.

One honest limitation: the API does not distinguish ``events.delete`` from a
cancellation - both come back as ``status: cancelled``. Through this adapter a
hard delete reads as a cancellation in the change feed.

The service object is duck-typed on the ``googleapiclient`` Resource interface
(``events().get/list/insert/patch/move/delete(...).execute()``) so tests inject a
fake; ``from_service_account_file`` builds the real client.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from receipts.models import (
    Appointment,
    AppointmentStatus,
    Change,
    Entity,
)

PATIENT_PROPERTY = "patientId"
REASON_PROPERTY = "reason"
ACTOR_PROPERTY = "actor"


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _private(ev: dict[str, Any]) -> dict[str, str]:
    return ev.get("extendedProperties", {}).get("private", {})


def event_to_appointment(provider: str, ev: dict[str, Any]) -> Appointment:
    """Map one Calendar event to the appointment row shape the auditor knows."""
    start = _parse(ev["start"]["dateTime"])
    end = _parse(ev["end"]["dateTime"])
    props = _private(ev)
    return Appointment(
        id=ev["id"],
        patient_id=props.get(PATIENT_PROPERTY, ""),
        provider=provider,
        start=start,
        duration_min=int((end - start).total_seconds() // 60),
        reason=props.get(REASON_PROPERTY, ev.get("summary", "")),
        status=(
            AppointmentStatus.CANCELLED
            if ev.get("status") == "cancelled"
            else AppointmentStatus.BOOKED
        ),
    )


def appointment_to_row(apt: Appointment) -> dict[str, Any]:
    """The same dict shape the SQLite journal carries, so the auditor cannot
    tell which backend produced the change feed."""
    return {
        "id": apt.id,
        "patient_id": apt.patient_id,
        "provider": apt.provider,
        "start": _rfc3339(apt.start),
        "duration_min": apt.duration_min,
        "reason": apt.reason,
        "status": apt.status.value,
    }


# ------------------------------- snapshots --------------------------------- #


@dataclass
class SnapshotCache:
    """Last-seen event bodies, optionally persisted as JSON.

    Holds both the event snapshots (keyed by event id) and the per-calendar
    sync token, so a process restart can resume incremental sync.
    """

    path: Path | None = None
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    calendars: dict[str, str] = field(default_factory=dict)  # event id -> calendar id
    sync_tokens: dict[str, str] = field(default_factory=dict)  # calendar id -> token

    @classmethod
    def load(cls, path: Path) -> SnapshotCache:
        if not path.exists():
            return cls(path=path)
        raw = json.loads(path.read_text())
        return cls(
            path=path,
            events=raw.get("events", {}),
            calendars=raw.get("calendars", {}),
            sync_tokens=raw.get("sync_tokens", {}),
        )

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "events": self.events,
                    "calendars": self.calendars,
                    "sync_tokens": self.sync_tokens,
                },
                indent=1,
            )
        )

    def update(self, calendar_id: str, ev: dict[str, Any]) -> None:
        self.events[ev["id"]] = ev
        self.calendars[ev["id"]] = calendar_id

    def forget(self, event_id: str) -> None:
        self.events.pop(event_id, None)
        self.calendars.pop(event_id, None)


# --------------------------------- reader ---------------------------------- #


class GoogleCalendarReader:
    """``CalendarReader`` against the Google Calendar API."""

    def __init__(
        self,
        service: Any,
        calendar_ids_by_provider: dict[str, str],
        *,
        cache: SnapshotCache | None = None,
    ) -> None:
        self._service = service
        self._calendars = dict(calendar_ids_by_provider)
        self._cache = cache or SnapshotCache()

    # -- lookups ------------------------------------------------------------ #

    def _provider_for(self, calendar_id: str) -> str:
        for provider, cal_id in self._calendars.items():
            if cal_id == calendar_id:
                return provider
        return calendar_id

    def _list(self, calendar_id: str, **params: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        request = self._service.events().list(calendarId=calendar_id, singleEvents=True, **params)
        while request is not None:
            page = request.execute()
            items.extend(page.get("items", []))
            request = self._service.events().list_next(request, page)
        return items

    def get_appointment(self, appointment_id: str) -> Appointment | None:
        calendar_id = self._cache.calendars.get(appointment_id)
        candidates = [calendar_id] if calendar_id else list(self._calendars.values())
        for cal_id in candidates:
            try:
                ev = self._service.events().get(calendarId=cal_id, eventId=appointment_id).execute()
            except Exception:
                continue
            return event_to_appointment(self._provider_for(cal_id), ev)
        return None

    def list_appointments(
        self,
        *,
        patient_id: str | None = None,
        provider: str | None = None,
        window: tuple[datetime, datetime] | None = None,
        include_cancelled: bool = False,
    ) -> list[Appointment]:
        params: dict[str, Any] = {}
        if window:
            params["timeMin"], params["timeMax"] = _rfc3339(window[0]), _rfc3339(window[1])
        if include_cancelled:
            params["showDeleted"] = True
        if patient_id:
            params["privateExtendedProperty"] = f"{PATIENT_PROPERTY}={patient_id}"
        cal_ids = [self._calendars[provider]] if provider else list(self._calendars.values())
        out = []
        for cal_id in cal_ids:
            for ev in self._list(cal_id, **params):
                if ev.get("status") == "cancelled" and not include_cancelled:
                    continue
                out.append(event_to_appointment(self._provider_for(cal_id), ev))
        return out

    # -- sync + change feed -------------------------------------------------- #

    def sync(self) -> None:
        """Refresh the snapshot cache, incrementally when a sync token exists."""
        for cal_id in self._calendars.values():
            token = self._cache.sync_tokens.get(cal_id)
            params: dict[str, Any] = {"showDeleted": True}
            if token:
                params["syncToken"] = token
            items: list[dict[str, Any]] = []
            request = self._service.events().list(calendarId=cal_id, **params)
            while request is not None:
                page = request.execute()
                items.extend(page.get("items", []))
                next_token = page.get("nextSyncToken")
                request = self._service.events().list_next(request, page)
            for ev in items:
                self._cache.update(cal_id, ev)
            if next_token:
                self._cache.sync_tokens[cal_id] = next_token
        self._cache.save()

    def changes(self, since: datetime, until: datetime) -> list[Change]:
        """Every mutation with ``since <= updated <= until``, oldest first.

        ``before`` is the cached snapshot from the last ``sync`` (or ``changes``)
        call - sync before the window you audit. Events the cache never saw have
        no before-image and read as inserts.
        """
        found: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []
        for cal_id in self._calendars.values():
            events = self._list(cal_id, updatedMin=_rfc3339(since), showDeleted=True)
            for ev in events:
                if _parse(ev["updated"]) > until:
                    continue
                before = self._cache.events.get(ev["id"])
                found.append((cal_id, ev, before))
        found.sort(key=lambda item: _parse(item[1]["updated"]))
        changes: list[Change] = []
        for seq, (cal_id, ev, before) in enumerate(found, start=1):
            apt = event_to_appointment(self._provider_for(cal_id), ev)
            props = _private(ev)
            changes.append(
                Change(
                    seq=seq,
                    entity=Entity.APPOINTMENT,
                    entity_id=apt.id,
                    op="insert" if before is None else "update",
                    before=(
                        appointment_to_row(event_to_appointment(self._provider_for(cal_id), before))
                        if before
                        else None
                    ),
                    after=appointment_to_row(apt),
                    actor=props.get(ACTOR_PROPERTY, ev.get("creator", {}).get("email", "unknown")),
                    at=_parse(ev["updated"]),
                )
            )
            self._cache.update(cal_id, ev)
        self._cache.save()
        return changes


# --------------------------------- writer ---------------------------------- #


class GoogleCalendarAdapter(GoogleCalendarReader):
    """``CalendarAdapter``: adds the writes the agent performs.

    ``actor`` is stamped on every event the writer touches, so the change feed
    can attribute the write. ``clock`` supplies created/updated times to
    backends (like the test fake) that do not stamp their own.
    """

    def __init__(
        self,
        service: Any,
        calendar_ids_by_provider: dict[str, str],
        *,
        actor: str,
        clock: Any | None = None,
        cache: SnapshotCache | None = None,
    ) -> None:
        super().__init__(service, calendar_ids_by_provider, cache=cache)
        self._actor = actor
        self._clock = clock

    def _now(self) -> datetime:
        return self._clock() if self._clock else datetime.now(UTC)

    def _body(
        self,
        *,
        patient_id: str,
        start: datetime,
        duration_min: int,
        reason: str,
        status: str = "confirmed",
    ) -> dict[str, Any]:
        end = start.timestamp() + duration_min * 60
        return {
            "summary": reason or "appointment",
            "status": status,
            "start": {"dateTime": _rfc3339(start)},
            "end": {"dateTime": _rfc3339(datetime.fromtimestamp(end, UTC))},
            "extendedProperties": {
                "private": {
                    PATIENT_PROPERTY: patient_id,
                    REASON_PROPERTY: reason,
                    ACTOR_PROPERTY: self._actor,
                }
            },
        }

    def create_appointment(
        self,
        *,
        patient_id: str,
        provider: str,
        start: datetime,
        duration_min: int = 30,
        reason: str = "",
    ) -> Appointment:
        body = self._body(
            patient_id=patient_id, start=start, duration_min=duration_min, reason=reason
        )
        ev = (
            self._service.events().insert(calendarId=self._calendars[provider], body=body).execute()
        )
        return event_to_appointment(provider, ev)

    def _find(self, appointment_id: str) -> tuple[str, dict[str, Any]]:
        calendar_id = self._cache.calendars.get(appointment_id)
        candidates = [calendar_id] if calendar_id else list(self._calendars.values())
        for cal_id in candidates:
            try:
                ev = self._service.events().get(calendarId=cal_id, eventId=appointment_id).execute()
                return cal_id, ev  # type: ignore[return-value]
            except Exception:
                continue
        from receipts.sor.base import RecordNotFound

        raise RecordNotFound(f"appointment {appointment_id} not found")

    def reschedule_appointment(self, appointment_id: str, new_start: datetime) -> Appointment:
        cal_id, ev = self._find(appointment_id)
        start = _parse(ev["start"]["dateTime"])
        end = _parse(ev["end"]["dateTime"])
        duration = end - start
        ev["start"] = {"dateTime": _rfc3339(new_start)}
        ev["end"] = {"dateTime": _rfc3339(new_start + duration)}
        ev.setdefault("extendedProperties", {}).setdefault("private", {})[ACTOR_PROPERTY] = (
            self._actor
        )
        updated = (
            self._service.events()
            .patch(calendarId=cal_id, eventId=appointment_id, body=ev)
            .execute()
        )
        return event_to_appointment(self._provider_for(cal_id), updated)

    def update_appointment(self, appointment_id: str, **fields: Any) -> Appointment:
        cal_id, ev = self._find(appointment_id)
        provider = self._provider_for(cal_id)
        props = ev.setdefault("extendedProperties", {}).setdefault("private", {})
        if "patient_id" in fields:
            props[PATIENT_PROPERTY] = fields["patient_id"]
        if "reason" in fields:
            props[REASON_PROPERTY] = fields["reason"]
            ev["summary"] = fields["reason"] or "appointment"
        start = _parse(ev["start"]["dateTime"])
        end = _parse(ev["end"]["dateTime"])
        if "start" in fields:
            duration = end - start
            start = fields["start"]
            end = start + duration
        if "duration_min" in fields:
            from datetime import timedelta

            end = start + timedelta(minutes=fields["duration_min"])
        ev["start"] = {"dateTime": _rfc3339(start)}
        ev["end"] = {"dateTime": _rfc3339(end)}
        if "status" in fields:
            ev["status"] = (
                "cancelled"
                if fields["status"] == AppointmentStatus.CANCELLED.value
                else "confirmed"
            )
        props[ACTOR_PROPERTY] = self._actor
        if "provider" in fields and fields["provider"] != provider:
            # Moving providers means moving calendars.
            moved = (
                self._service.events()
                .move(
                    calendarId=cal_id,
                    eventId=appointment_id,
                    destination=self._calendars[fields["provider"]],
                )
                .execute()
            )
            cal_id, ev = self._calendars[fields["provider"]], moved
            provider = fields["provider"]
        updated = (
            self._service.events()
            .patch(calendarId=cal_id, eventId=appointment_id, body=ev)
            .execute()
        )
        return event_to_appointment(provider, updated)

    def cancel_appointment(self, appointment_id: str) -> Appointment:
        return self.update_appointment(appointment_id, status=AppointmentStatus.CANCELLED.value)

    def delete_appointment(self, appointment_id: str) -> None:
        cal_id, _ = self._find(appointment_id)
        self._service.events().delete(calendarId=cal_id, eventId=appointment_id).execute()

    @classmethod
    def from_service_account_file(
        cls,
        path: str,
        calendar_ids_by_provider: dict[str, str],
        *,
        actor: str,
        cache_path: str | None = None,
    ) -> GoogleCalendarAdapter:
        """Build the real client. Imports google-api-python-client lazily."""
        from google.oauth2 import service_account  # type: ignore[import-not-found]
        from googleapiclient.discovery import build  # type: ignore[import-not-found]

        creds = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        cache = SnapshotCache.load(Path(cache_path)) if cache_path else None
        return cls(service, calendar_ids_by_provider, actor=actor, cache=cache)
