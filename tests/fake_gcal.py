"""In-memory stand-in for googleapiclient's Calendar v3 service.

Implements just the surface the adapter uses, with googleapiclient's
request/execute shape: events().get/list/insert/patch/move/delete(...).execute().
Timestamps come from an injected clock so tests stay deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


class HttpError404(Exception):
    """The one error shape the adapter must survive: event not found."""


class _Request:
    def __init__(self, fn: Callable[[], Any]) -> None:
        self._fn = fn

    def execute(self) -> Any:
        return self._fn()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class _Events:
    def __init__(self, service: FakeCalendarService) -> None:
        self._svc = service

    # -- reads --------------------------------------------------------------- #

    def get(self, calendarId: str, eventId: str) -> _Request:  # noqa: N803
        def run() -> dict[str, Any]:
            ev = self._svc._cals.get(calendarId, {}).get(eventId)
            if ev is None or ev.get("_purged"):
                raise HttpError404(eventId)
            return dict(ev)

        return _Request(run)

    def list(  # noqa: N803, PLR0913
        self,
        calendarId: str,
        singleEvents: bool = True,
        timeMin: str | None = None,
        timeMax: str | None = None,
        updatedMin: str | None = None,
        showDeleted: bool = False,
        privateExtendedProperty: str | None = None,
        syncToken: str | None = None,
        pageToken: str | None = None,
    ) -> _Request:
        def run() -> dict[str, Any]:
            svc = self._svc
            rev = svc._revs.get(calendarId, 0)
            if syncToken is not None and int(syncToken) > rev:
                raise HttpError404("sync token expired")  # real API: 410 Gone
            items = []
            for ev in svc._cals.get(calendarId, {}).values():
                if ev.get("_purged") and not showDeleted:
                    continue
                if syncToken is not None and ev["_rev"] <= int(syncToken):
                    continue
                if ev.get("status") == "cancelled" and not showDeleted:
                    continue
                if timeMin and _parse(ev["start"]["dateTime"]) < _parse(timeMin):
                    continue
                if timeMax and _parse(ev["start"]["dateTime"]) >= _parse(timeMax):
                    continue
                if updatedMin and _parse(ev["updated"]) < _parse(updatedMin):
                    continue
                if privateExtendedProperty:
                    key, _, value = privateExtendedProperty.partition("=")
                    props = ev.get("extendedProperties", {}).get("private", {})
                    if props.get(key) != value:
                        continue
                items.append(dict(ev))
            items.sort(key=lambda e: e["start"]["dateTime"])
            return {"items": items, "nextSyncToken": str(rev)}

        return _Request(run)

    def list_next(self, request: _Request, page: dict[str, Any]) -> None:
        return None  # the fake never paginates

    # -- writes --------------------------------------------------------------- #

    def insert(self, calendarId: str, body: dict[str, Any]) -> _Request:  # noqa: N803
        def run() -> dict[str, Any]:
            svc = self._svc
            svc._counter += 1
            ev = dict(body)
            ev["id"] = f"evt_{svc._counter:04d}"
            svc._stamp(calendarId, ev, created=True)
            svc._cals.setdefault(calendarId, {})[ev["id"]] = ev
            return dict(ev)

        return _Request(run)

    def patch(self, calendarId: str, eventId: str, body: dict[str, Any]) -> _Request:  # noqa: N803
        def run() -> dict[str, Any]:
            ev = self._svc._cals.get(calendarId, {}).get(eventId)
            if ev is None or ev.get("_purged"):
                raise HttpError404(eventId)
            ev.update(body)
            ev["id"] = eventId
            self._svc._stamp(calendarId, ev)
            return dict(ev)

        return _Request(run)

    def move(self, calendarId: str, eventId: str, destination: str) -> _Request:  # noqa: N803
        def run() -> dict[str, Any]:
            ev = self._svc._cals.get(calendarId, {}).get(eventId)
            if ev is None or ev.get("_purged"):
                raise HttpError404(eventId)
            ev = self._svc._cals[calendarId].pop(eventId)
            self._svc._stamp(destination, ev)
            self._svc._cals.setdefault(destination, {})[eventId] = ev
            return dict(ev)

        return _Request(run)

    def delete(self, calendarId: str, eventId: str) -> _Request:  # noqa: N803
        def run() -> None:
            ev = self._svc._cals.get(calendarId, {}).get(eventId)
            if ev is None or ev.get("_purged"):
                raise HttpError404(eventId)
            # Like the real API: get starts 404ing, and the event only stays
            # visible in the sync feed (showDeleted) as status "cancelled".
            ev["status"] = "cancelled"
            ev["_purged"] = True
            self._svc._stamp(calendarId, ev)

        return _Request(run)


class FakeCalendarService:
    """Duck-type of the googleapiclient Calendar v3 service."""

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._cals: dict[str, dict[str, dict[str, Any]]] = {}
        self._revs: dict[str, int] = {}
        self._counter = 0

    def events(self) -> _Events:
        return _Events(self)

    def _stamp(self, calendar_id: str, ev: dict[str, Any], *, created: bool = False) -> None:
        now = self._clock().astimezone(UTC)
        ts = now.isoformat().replace("+00:00", "Z")
        if created:
            ev["created"] = ts
            ev.setdefault("creator", {})
        ev["updated"] = ts
        self._revs[calendar_id] = self._revs.get(calendar_id, 0) + 1
        ev["_rev"] = self._revs[calendar_id]
