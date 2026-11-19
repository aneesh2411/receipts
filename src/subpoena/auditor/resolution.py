"""Verified resolution: a fixed mismatch closes only on repeated matching evidence.

A reviewer saying "fixed" is an assertion. This module re-reads the system of
record and compares today's state with what the original claim said. A claim
counts as resolved only when two snapshots, taken at least ``settle`` apart,
both match. One match is not enough: a write can land late, or be rolled back.
No model is involved; the decision is a pure function of the snapshots.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from subpoena.models import (
    AppointmentBooked,
    Cancelled,
    Claim,
    Frozen,
    PatientRef,
    Rescheduled,
)
from subpoena.sor.base import SystemOfRecordReader


class Resolution(StrEnum):
    VERIFIED_CLOSED = "verified_closed"  # two matching snapshots, far enough apart
    PENDING = "pending"  # not matching yet, or matched only once
    INCONCLUSIVE = "inconclusive"  # the evidence could not be read or compared


class Snapshot(Frozen):
    observed_at: datetime
    matches: bool | None  # None = could not be evaluated
    detail: str
    digest: str  # hash of the evidence read, so two snapshots can be told apart


def _digest(rows: object) -> str:
    raw = json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _ids(sor: SystemOfRecordReader, ref: PatientRef | None) -> list[str]:
    if ref is None:
        return []
    found = sor.crm.find_patients(phone=ref.phone) if ref.phone else []
    return [p.id for p in (found or sor.crm.find_patients(name=ref.name))]


def _booked_at(sor: SystemOfRecordReader, ids: Sequence[str], start: datetime) -> list[str]:
    probe = (start, start + timedelta(minutes=1))
    return [
        a.id
        for pid in ids
        for a in sor.calendar.list_appointments(patient_id=pid, window=probe)
        if a.start == start
    ]


def take_snapshot(claim: Claim, sor: SystemOfRecordReader, now: datetime) -> Snapshot:
    """Compare the record as it stands now with what the original claim said."""
    try:
        if isinstance(claim, AppointmentBooked):
            ids = _ids(sor, claim.patient)
            if len(ids) != 1:
                return _unknown(now, "the patient cannot be resolved to exactly one record")
            hits = _booked_at(sor, ids, claim.start)
            return Snapshot(
                observed_at=now,
                matches=bool(hits),
                detail="booking present at the claimed time"
                if hits
                else "no booking at the claimed time",
                digest=_digest(hits),
            )
        if isinstance(claim, Cancelled):
            ids = _ids(sor, claim.patient)
            if len(ids) != 1:
                return _unknown(now, "the patient cannot be resolved to exactly one record")
            hits = _booked_at(sor, ids, claim.start)
            return Snapshot(
                observed_at=now,
                matches=not hits,
                detail="slot is clear" if not hits else "a booking still holds the claimed slot",
                digest=_digest(hits),
            )
        if isinstance(claim, Rescheduled):
            ids = _ids(sor, claim.patient)
            if len(ids) != 1:
                return _unknown(now, "the patient cannot be resolved to exactly one record")
            old = _booked_at(sor, ids, claim.old_start)
            new = _booked_at(sor, ids, claim.new_start)
            ok = bool(new) and not old
            return Snapshot(
                observed_at=now,
                matches=ok,
                detail="moved: new slot held, old slot clear"
                if ok
                else f"old slot holds {len(old)}, new slot holds {len(new)}",
                digest=_digest([old, new]),
            )
    except Exception as exc:  # an unreadable source is never a pass or a fail
        return _unknown(now, f"evidence source could not be read ({type(exc).__name__})")
    return _unknown(now, f"no state check exists for {claim.type} claims")


def _unknown(now: datetime, detail: str) -> Snapshot:
    return Snapshot(observed_at=now, matches=None, detail=detail, digest=_digest(detail))


def decide(snapshots: Sequence[Snapshot], settle: timedelta = timedelta(minutes=5)) -> Resolution:
    """Close only when the two latest snapshots both match and are ``settle`` apart."""
    if not snapshots:
        return Resolution.PENDING
    ordered = sorted(snapshots, key=lambda s: s.observed_at)
    last = ordered[-1]
    if last.matches is None:
        return Resolution.INCONCLUSIVE
    if not last.matches or len(ordered) < 2:
        return Resolution.PENDING
    previous = ordered[-2]
    if previous.matches is True and last.observed_at - previous.observed_at >= settle:
        return Resolution.VERIFIED_CLOSED
    return Resolution.PENDING
