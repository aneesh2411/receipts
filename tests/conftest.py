"""Shared fixtures: a seeded clinic and helpers to hand-build calls."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from subpoena.auditor import Auditor
from subpoena.models import AuditReport, CallRecord, Claim, Patient, PatientRef, Turn
from subpoena.scenarios.world import CALL_START, CLINIC, ROSTER
from subpoena.sor import SqliteStore, SystemOfRecord
from subpoena.suspect import AGENT_ID, SimClock


@dataclass
class Clinic:
    store: SqliteStore
    clock: SimClock
    agent: SystemOfRecord
    patients: dict[str, Patient]

    def patient(self, ref: PatientRef) -> Patient:
        return self.patients[ref.name]

    def as_actor(self, actor: str, when: datetime | None = None) -> SystemOfRecord:
        moment = when or self.clock.now()
        return self.store.session(actor, lambda: moment)

    def call(
        self,
        claims: Sequence[Claim] = (),
        *,
        caller: PatientRef = ROSTER[0],
        agent_lines: Sequence[str] = (),
        minutes: int = 2,
    ) -> CallRecord:
        """A call record covering [CALL_START, CALL_START + minutes]."""
        turns = tuple(
            Turn(index=i, speaker="agent", text=text, at=CALL_START + timedelta(seconds=5 * i))
            for i, text in enumerate(agent_lines)
        )
        return CallRecord(
            call_id="call-test",
            agent_id=AGENT_ID,
            caller=caller,
            started_at=CALL_START,
            ended_at=CALL_START + timedelta(minutes=minutes),
            transcript=turns,
            claims=tuple(claims),
        )

    def audit(self, call: CallRecord, **options: object) -> AuditReport:
        audited_at = call.ended_at + timedelta(minutes=1)
        reader = options.pop("reader", None) or self.store.session("auditor", lambda: audited_at)
        return Auditor(reader, clinic=CLINIC, clock=lambda: audited_at, **options).audit(
            call, audit_id="aud-test"
        )


@pytest.fixture
def clinic() -> Iterator[Clinic]:
    store = SqliteStore()
    yesterday = CALL_START - timedelta(days=1)
    seeder = store.session("seed", lambda: yesterday)
    patients = {
        ref.name: seeder.crm.create_patient(name=ref.name, phone=ref.phone or "") for ref in ROSTER
    }
    clock = SimClock(CALL_START + timedelta(seconds=30))
    yield Clinic(store, clock, store.session(AGENT_ID, clock), patients)
    store.close()
