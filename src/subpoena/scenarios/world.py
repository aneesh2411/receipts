"""Scenario definition and the deterministic machinery that plays one out.

A scenario is fully specified by data: the clinic's starting state, the caller's
script, which faults fire, and what a correct auditor must conclude. Playing the
same scenario twice yields byte-identical calls and reports.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from subpoena.auditor import Auditor, ClaimExtractor, NaiveAuditor, Sealer
from subpoena.models import AuditReport, PatientRef, VerdictStatus
from subpoena.sor import SqliteStore, with_outage
from subpoena.suspect import (
    AGENT_ID,
    CallResult,
    FaultMode,
    ForcedFaults,
    Narrator,
    ReceptionistAgent,
    SimClock,
    Step,
)
from subpoena.util import ClinicConfig

CLINIC = ClinicConfig()
TZ = ZoneInfo(CLINIC.tz)
MONDAY = datetime(2026, 3, 2, tzinfo=TZ)  # week before US daylight saving starts


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """Clinic-local time, ``day`` days after Monday 2 March 2026."""
    return MONDAY + timedelta(days=day, hours=hour, minutes=minute)


CALL_START = at(0, 9, 5)

MAYA = PatientRef(name="Maya Chen", phone="+15550101001")
DANIEL = PatientRef(name="Daniel Okafor", phone="+15550101002")
PRIYA = PatientRef(name="Priya Raman", phone="+15550101003")
TOM = PatientRef(name="Tom Becker", phone="+15550101004")
SOFIA = PatientRef(name="Sofia Alvarez", phone="+15550101005")
LEO = PatientRef(name="Leo Martins", phone="+15550101099")  # not on file: a new patient
ROSTER: tuple[PatientRef, ...] = (MAYA, DANIEL, PRIYA, TOM, SOFIA)

PATEL, KIM, OSEI = "Dr. Patel", "Dr. Kim", "Dr. Osei"


@dataclass(frozen=True)
class SeedAppointment:
    patient: PatientRef
    provider: str
    start: datetime
    duration_min: int = 30
    reason: str = "cleaning"
    cancelled: bool = False
    by_staff_during_call: bool = False  # written by a human while the call is in progress


Expected = tuple[str, VerdictStatus]
# (claim type, expected status, identity label): separately reviewed data naming
# which appointment, message or ticket an expectation is about. See
# evals.score.claim_identity for the label format.
ExpectedV2 = tuple[str, VerdictStatus, str]


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    story: str
    steps: tuple[Step, ...]
    expected_claims: tuple[Expected, ...]
    expected_findings: tuple[str, ...] = ()  # finding codes, e.g. "double_booking"
    caller: PatientRef = MAYA
    faults: Mapping[int, frozenset[FaultMode]] = field(default_factory=dict)
    seed: tuple[SeedAppointment, ...] = ()
    extra_patients: tuple[PatientRef, ...] = ()  # e.g. a second patient with the same name
    tags: tuple[str, ...] = ()
    hard_phrasing: bool = False
    outage: tuple[str, ...] = ()  # adapters that are down when the audit runs
    known_gap: str | None = None  # why the auditor is expected to get this one wrong
    # Identity-labelled twin of expected_claims, attached after construction once
    # reviewed (see golden._V2). Keyword-only position: several scenarios pass
    # expected_findings positionally.
    expected_claims_v2: tuple[ExpectedV2, ...] = ()

    @property
    def fault_modes(self) -> frozenset[FaultMode]:
        return frozenset(m for modes in self.faults.values() for m in modes)

    @property
    def expected_dirty(self) -> bool:
        return bool(self.expected_findings) or any(
            status is not VerdictStatus.VERIFIED for _, status in self.expected_claims
        )


@dataclass(frozen=True)
class World:
    store: SqliteStore
    clock: SimClock


@dataclass(frozen=True)
class ScenarioRun:
    scenario: Scenario
    result: CallResult
    report: AuditReport


def build_world(scenario: Scenario, store: SqliteStore | None = None) -> World:
    """Create the clinic's state as it stood when the phone rang."""
    store = store or SqliteStore()
    yesterday = CALL_START - timedelta(days=1)
    seeder = store.session("seed", lambda: yesterday)
    staff = store.session("staff:front-desk", lambda: CALL_START + timedelta(seconds=5))
    ids = {
        ref.phone: seeder.crm.create_patient(name=ref.name, phone=ref.phone or "").id
        for ref in ROSTER
    }
    for ref in scenario.extra_patients:
        seeder.crm.create_patient(name=ref.name, phone=ref.phone or "")
    for appt in scenario.seed:
        writer = staff if appt.by_staff_during_call else seeder
        created = writer.calendar.create_appointment(
            patient_id=ids[appt.patient.phone],
            provider=appt.provider,
            start=appt.start,
            duration_min=appt.duration_min,
            reason=appt.reason,
        )
        if appt.cancelled:
            writer.calendar.cancel_appointment(created.id)
    return World(store=store, clock=SimClock(CALL_START))


def run_suspect(scenario: Scenario, world: World) -> CallResult:
    # The platform session stamps every write with the call id, so the journal
    # can attribute a mutation to one call, not just to the shared agent identity.
    call_id = f"call-{scenario.id}"
    agent = ReceptionistAgent(
        world.store.session(f"{AGENT_ID}:{call_id}", world.clock),
        world.clock,
        narrator=Narrator(random.Random(scenario.id), TZ, hard=scenario.hard_phrasing),
        clinic=CLINIC,
        faults=ForcedFaults(scenario.faults),
    )
    return agent.handle_call(call_id, scenario.caller, scenario.steps)


def audit_call(
    scenario: Scenario,
    world: World,
    result: CallResult,
    *,
    auditor: Literal["subpoena", "naive"] = "receipts",
    extractor: ClaimExtractor | None = None,
    sealer: Sealer | None = None,
    options: Mapping[str, Any] | None = None,
) -> AuditReport:
    """Audit the call. ``options`` are extra ``Auditor`` arguments (used for ablations)."""
    audited_at = result.call.ended_at + timedelta(minutes=1)
    reader = world.store.session("auditor", lambda: audited_at)
    if scenario.outage:
        reader = with_outage(reader, *scenario.outage)
    if auditor == "naive":
        return NaiveAuditor(reader, clinic=CLINIC, clock=lambda: audited_at).audit(
            result.call, audit_id=f"naive-{scenario.id}"
        )
    return Auditor(
        reader,
        clinic=CLINIC,
        extractor=extractor,
        sealer=sealer,
        clock=lambda: audited_at,
        **(options or {}),
    ).audit(result.call, audit_id=f"aud-{scenario.id}")


def run_scenario(
    scenario: Scenario,
    *,
    auditor: Literal["subpoena", "naive"] = "receipts",
    extractor: ClaimExtractor | None = None,
    sealer: Sealer | None = None,
    options: Mapping[str, Any] | None = None,
) -> ScenarioRun:
    world = build_world(scenario)
    try:
        result = run_suspect(scenario, world)
        report = audit_call(
            scenario,
            world,
            result,
            auditor=auditor,
            extractor=extractor,
            sealer=sealer,
            options=options,
        )
    finally:
        world.store.close()
    return ScenarioRun(scenario=scenario, result=result, report=report)
