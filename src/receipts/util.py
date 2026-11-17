"""Normalisation and time helpers shared by the suspect, the store and the auditor."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo


def norm_phone(raw: str) -> str:
    """Reduce a phone number to a comparable E.164-ish form (US default)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits


def norm_text(raw: str) -> str:
    return " ".join(raw.casefold().split())


def to_utc_iso(dt: datetime) -> str:
    """Canonical storage form: UTC, second precision, sortable as text."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime is not allowed in the system of record")
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ClinicConfig:
    """The clinic's operating rules: used by the honest agent and by policy checks."""

    name: str = "Brightside Dental"
    tz: str = "America/New_York"
    open_hour: int = 8
    close_hour: int = 17
    open_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    slot_minutes: int = 30

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    def is_open(self, start: datetime, duration_min: int) -> bool:
        local = start.astimezone(self.zone)
        end = local + timedelta(minutes=duration_min)
        opens = local.replace(hour=self.open_hour, minute=0, second=0, microsecond=0)
        closes = local.replace(hour=self.close_hour, minute=0, second=0, microsecond=0)
        return local.weekday() in self.open_weekdays and opens <= local and end <= closes


# --------------------------------------------------------------------------- #
# Spoken time: the format agents say aloud and write into SMS bodies
# --------------------------------------------------------------------------- #

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_SPOKEN_TIME = re.compile(
    r"(?P<month>" + "|".join(_MONTHS) + r")\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(?P<year>\d{4}))?,?\s+at\s+"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)\b",
    re.IGNORECASE,
)


def _clock(local: datetime) -> str:
    hour = local.hour % 12 or 12
    return f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def speak(dt: datetime, tz: tzinfo) -> str:
    """Render a time the way a receptionist says it: 'Tuesday, March 3 at 2:30 PM'."""
    local = dt.astimezone(tz)
    return f"{local:%A}, {local:%B} {local.day} at {_clock(local)}"


def show(dt: datetime, tz: tzinfo) -> str:
    """Compact unambiguous display form used in evidence tables."""
    local = dt.astimezone(tz)
    return f"{local:%a %b} {local.day} {local.year}, {_clock(local)} {local:%Z}"


def find_times(text: str, *, ref: datetime, tz: tzinfo) -> list[datetime]:
    """Find every spoken-format time in ``text``.

    A spoken time carries no year, so it is resolved against ``ref`` (the call
    time): the nearest occurrence that is not more than ~6 months in the past.
    """
    ref_local = ref.astimezone(tz)
    found: list[datetime] = []
    for m in _SPOKEN_TIME.finditer(text):
        hour = int(m["hour"]) % 12 + (12 if m["ampm"].lower() == "pm" else 0)
        minute = int(m["minute"] or 0)
        month, day = _MONTHS[m["month"].lower()], int(m["day"])
        year = int(m["year"]) if m["year"] else ref_local.year
        try:
            candidate = datetime(year, month, day, hour, minute, tzinfo=tz)
            if not m["year"] and candidate < ref_local - timedelta(days=180):
                candidate = datetime(year + 1, month, day, hour, minute, tzinfo=tz)
        except ValueError:
            continue  # not a real date/time (e.g. "February 30"): ignore it
        found.append(candidate)
    return found
