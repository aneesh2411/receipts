"""Working state for one audit: the call, the evidence and what has been used."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from receipts.auditor.delta import SOURCE, ChangeKind, NetChange, collapse
from receipts.models import Appointment, CallRecord, Entity, Evidence, PatientRef, TrailEvent
from receipts.sor.base import AdapterUnavailable, SystemOfRecordReader
from receipts.util import ClinicConfig, norm_phone, norm_text, show


@dataclass(frozen=True)
class Match:
    """The journal changes a claim has been paired with."""

    primary: NetChange | None
    secondary: NetChange | None = None

    @property
    def changes(self) -> tuple[NetChange, ...]:
        return tuple(c for c in (self.primary, self.secondary) if c is not None)


@dataclass
class AuditContext:
    call: CallRecord
    sor: SystemOfRecordReader
    clinic: ClinicConfig
    window: tuple[datetime, datetime]
    delta: dict[Entity, list[NetChange] | None] = field(default_factory=dict)
    errors: dict[Entity, str] = field(default_factory=dict)
    trail: list[TrailEvent] = field(default_factory=list)
    _consumed: set[tuple[Entity, str]] = field(default_factory=set)
    _patient_cache: dict[tuple[str, str | None], frozenset[str]] = field(default_factory=dict)

    @classmethod
    def open(
        cls, call: CallRecord, sor: SystemOfRecordReader, clinic: ClinicConfig, grace: timedelta
    ) -> AuditContext:
        """Pull each system's change feed for the call window, attributed to the agent."""
        ctx = cls(call, sor, clinic, (call.started_at, call.ended_at + grace))
        feeds = {
            Entity.APPOINTMENT: sor.calendar,
            Entity.PATIENT: sor.crm,
            Entity.MESSAGE: sor.messages,
            Entity.TICKET: sor.tickets,
        }
        for entity, feed in feeds.items():
            try:
                changes = feed.changes(*ctx.window)
            except AdapterUnavailable as exc:
                ctx.delta[entity] = None
                ctx.errors[entity] = str(exc)
                ctx.log("evidence", f"{SOURCE[entity]}: UNAVAILABLE ({exc}). Will not guess.")
                continue
            mine = [c for c in changes if c.actor == call.agent_id]
            ctx.delta[entity] = collapse(mine)
            others = len(changes) - len(mine)
            note = f"; {others} by other actors ignored" if others else ""
            ctx.log(
                "evidence",
                f"{SOURCE[entity]}: {len(mine)} journal row(s) by {call.agent_id} "
                f"in the call window{note}",
            )
        return ctx

    # -- bookkeeping -------------------------------------------------------- #

    @property
    def tz(self) -> ZoneInfo:
        return self.clinic.zone

    def log(self, stage: str, message: str) -> None:
        self.trail.append(TrailEvent(seq=len(self.trail) + 1, stage=stage, message=message))

    def free(self, entity: Entity) -> list[NetChange]:
        """Net changes by the agent that no claim has accounted for yet."""
        return [
            nc
            for nc in self.delta.get(entity) or []
            if nc.key not in self._consumed and nc.kind is not ChangeKind.TRANSIENT
        ]

    def transient(self, entity: Entity) -> list[NetChange]:
        return [nc for nc in self.delta.get(entity) or [] if nc.kind is ChangeKind.TRANSIENT]

    def touched(self, entity: Entity) -> list[NetChange]:
        return list(self.delta.get(entity) or [])

    def consume(self, match: Match) -> None:
        self._consumed.update(nc.key for nc in match.changes)

    # -- lookups against current state ------------------------------------- #

    def patient_ids(self, ref: PatientRef | None) -> frozenset[str]:
        """Resolve how the call named a person to CRM ids: phone first, then name."""
        if ref is None:
            return frozenset()
        key = (norm_text(ref.name), norm_phone(ref.phone) if ref.phone else None)
        if key not in self._patient_cache:
            found = self.sor.crm.find_patients(phone=ref.phone) if ref.phone else []
            if not found:
                found = self.sor.crm.find_patients(name=ref.name)
            self._patient_cache[key] = frozenset(p.id for p in found)
        return self._patient_cache[key]

    def patient_label(self, patient_id: str | None) -> str:
        if patient_id is None:
            return "no patient"
        patient = self.sor.crm.get_patient(patient_id)
        return f"{patient.name} ({patient.phone})" if patient else f"unknown ({patient_id})"

    def booked_at(self, patient_ids: frozenset[str], start: datetime) -> list[Appointment]:
        """Appointments currently on the books for these patients at exactly ``start``."""
        probe = (start, start + timedelta(minutes=1))
        return [
            appt
            for pid in sorted(patient_ids)
            for appt in self.sor.calendar.list_appointments(patient_id=pid, window=probe)
            if appt.start == start
        ]

    def show(self, dt: datetime) -> str:
        return show(dt, self.tz)

    def journal_evidence(self, entity: Entity, note: str) -> Evidence:
        lo, hi = self.window
        count = sum(len(nc.changes) for nc in self.touched(entity))
        return Evidence(
            source="journal",
            ref=f"{SOURCE[entity]} {lo.isoformat()} .. {hi.isoformat()}",
            note=f"{count} agent write(s) to {SOURCE[entity]} in the call window. {note}",
        )


def ref_label(ref: PatientRef | None) -> str:
    if ref is None:
        return "not stated"
    return f"{ref.name} ({norm_phone(ref.phone)})" if ref.phone else ref.name
