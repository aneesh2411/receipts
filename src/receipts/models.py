"""Typed domain models: claims, system-of-record records, verdicts and reports.

Every model is frozen. The auditor never mutates a claim or a record; it only
derives new values from them.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- #
# System-of-record records
# --------------------------------------------------------------------------- #

Channel = Literal["sms", "email"]
Priority = Literal["low", "normal", "urgent"]


class Entity(StrEnum):
    PATIENT = "patient"
    APPOINTMENT = "appointment"
    MESSAGE = "message"
    TICKET = "ticket"


class AppointmentStatus(StrEnum):
    BOOKED = "booked"
    CANCELLED = "cancelled"


class Patient(Frozen):
    id: str
    name: str
    phone: str
    email: str | None = None


class Appointment(Frozen):
    id: str
    patient_id: str
    provider: str
    start: AwareDatetime
    duration_min: int
    reason: str = ""
    status: AppointmentStatus = AppointmentStatus.BOOKED

    @property
    def end(self) -> AwareDatetime:
        return self.start + timedelta(minutes=self.duration_min)


class Message(Frozen):
    id: str
    recipient: str
    channel: Channel
    body: str
    status: Literal["sent", "failed"] = "sent"
    sent_at: AwareDatetime


class Ticket(Frozen):
    id: str
    patient_id: str | None = None
    summary: str
    priority: Priority = "normal"
    status: Literal["open", "closed"] = "open"
    created_at: AwareDatetime


class Change(Frozen):
    """One row of a system of record's change feed."""

    seq: int
    entity: Entity
    entity_id: str
    op: Literal["insert", "update", "delete"]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    actor: str
    at: AwareDatetime


# --------------------------------------------------------------------------- #
# Claims: what the agent says it did
# --------------------------------------------------------------------------- #


class PatientRef(Frozen):
    """How a call refers to a person: by name and (usually) phone, never by id."""

    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)


class ClaimSource(StrEnum):
    STRUCTURED = "structured"  # emitted by the agent's tool layer
    TRANSCRIPT = "transcript"  # recovered from what the caller was told


class ClaimBase(Frozen):
    claim_id: str = Field(min_length=1, max_length=80)
    turn_index: int = Field(ge=0)
    source: ClaimSource = ClaimSource.STRUCTURED
    utterance: str = Field(default="", max_length=4000)


class AppointmentBooked(ClaimBase):
    type: Literal["AppointmentBooked"] = "AppointmentBooked"
    patient: PatientRef
    start: AwareDatetime
    provider: str | None = Field(default=None, max_length=120)
    duration_min: int | None = Field(default=None, gt=0, le=480)
    reason: str | None = Field(default=None, max_length=200)


class Rescheduled(ClaimBase):
    type: Literal["Rescheduled"] = "Rescheduled"
    patient: PatientRef
    old_start: AwareDatetime
    new_start: AwareDatetime
    provider: str | None = Field(default=None, max_length=120)


class Cancelled(ClaimBase):
    type: Literal["Cancelled"] = "Cancelled"
    patient: PatientRef
    start: AwareDatetime


class ConfirmationSent(ClaimBase):
    type: Literal["ConfirmationSent"] = "ConfirmationSent"
    channel: Channel = "sms"
    to: str = Field(min_length=1, max_length=200)
    about_start: AwareDatetime | None = None


class HandoffCreated(ClaimBase):
    type: Literal["HandoffCreated"] = "HandoffCreated"
    patient: PatientRef | None = None
    summary: str = Field(default="", max_length=2000)
    priority: Priority | None = None


Claim = Annotated[
    AppointmentBooked | Rescheduled | Cancelled | ConfirmationSent | HandoffCreated,
    Field(discriminator="type"),
]

CLAIM_TYPES: tuple[str, ...] = (
    "AppointmentBooked",
    "Rescheduled",
    "Cancelled",
    "ConfirmationSent",
    "HandoffCreated",
)


# --------------------------------------------------------------------------- #
# Calls
# --------------------------------------------------------------------------- #


class Turn(Frozen):
    index: int = Field(ge=0)
    speaker: Literal["caller", "agent"]
    text: str = Field(max_length=4000)
    at: AwareDatetime


class CallRecord(Frozen):
    """Everything the auditor is given about a call. Nothing here is trusted."""

    call_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    agent_id: str = Field(min_length=1, max_length=120)
    caller: PatientRef
    started_at: AwareDatetime
    ended_at: AwareDatetime
    transcript: tuple[Turn, ...] = Field(default=(), max_length=500)
    claims: tuple[Claim, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def _window_is_ordered(self) -> CallRecord:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not be before started_at")
        return self

    @model_validator(mode="after")
    def _claim_ids_are_unique(self) -> CallRecord:
        seen: set[str] = set()
        for claim in self.claims:
            if claim.claim_id in seen:
                raise ValueError(f"duplicate claim_id {claim.claim_id!r}")
            seen.add(claim.claim_id)
        return self


# --------------------------------------------------------------------------- #
# Verdicts: what the auditor concluded
# --------------------------------------------------------------------------- #


class VerdictStatus(StrEnum):
    VERIFIED = "VERIFIED"  # the claimed action happened, exactly as claimed
    MISMATCH = "MISMATCH"  # something happened, but not what was claimed
    NOT_FOUND = "NOT_FOUND"  # no evidence the action happened at all
    UNVERIFIABLE = "UNVERIFIABLE"  # the evidence source could not be read


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_RANK: dict[Severity, int] = {s: i for i, s in enumerate(Severity)}


def max_severity(severities: list[Severity]) -> Severity:
    return max(severities, key=SEVERITY_RANK.__getitem__, default=Severity.INFO)


class CheckName(StrEnum):
    EXISTENCE = "existence"
    EXACTNESS = "exactness"
    SIDE_EFFECTS = "side_effects"


class Check(Frozen):
    name: CheckName
    passed: bool | None  # None = not applicable / could not be evaluated
    detail: str


class FieldDiff(Frozen):
    """One row of the claimed-versus-actual comparison."""

    field: str
    claimed: str
    actual: str
    match: bool


class Evidence(Frozen):
    source: str  # calendar | crm | messages | tickets | journal
    ref: str
    note: str
    record: dict[str, Any] | None = None


class Verdict(Frozen):
    claim: Claim
    status: VerdictStatus
    severity: Severity
    summary: str
    checks: tuple[Check, ...] = ()
    diffs: tuple[FieldDiff, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    remediation: str | None = None


class FindingKind(StrEnum):
    UNCLAIMED_WRITE = "UNCLAIMED_WRITE"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class Finding(Frozen):
    """A discrepancy that is not attached to any claim."""

    finding_id: str
    kind: FindingKind
    code: str
    severity: Severity
    summary: str
    evidence: tuple[Evidence, ...] = ()
    remediation: str | None = None


class Outcome(StrEnum):
    CLEAN = "CLEAN"
    DISCREPANCIES = "DISCREPANCIES"
    INCONCLUSIVE = "INCONCLUSIVE"


class TrailEvent(Frozen):
    seq: int
    stage: str
    message: str


class AuditStats(Frozen):
    claims: int
    verified: int
    mismatch: int
    not_found: int
    unverifiable: int
    findings: int
    trust_score: float | None
    max_severity: Severity


class Seal(Frozen):
    algorithm: Literal["sha256"] = "sha256"
    content_hash: str
    prev_hash: str
    chain_hash: str
    signature: str | None = None
    key_id: str | None = None


class AuditReport(Frozen):
    audit_id: str
    auditor: str
    created_at: AwareDatetime
    call: CallRecord
    outcome: Outcome
    verdicts: tuple[Verdict, ...]
    findings: tuple[Finding, ...]
    trail: tuple[TrailEvent, ...]
    stats: AuditStats
    seal: Seal | None = None
