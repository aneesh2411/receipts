"""The auditor.

Pipeline, in order:

1. **Collect claims**: structured claims plus anything the caller was told that
   was never logged as a claim.
2. **Pull evidence**: each system's change feed for the call window, attributed
   to the agent's identity and reduced to net changes.
3. **Reconcile**: pair claims with writes, exact matches first, then best partial.
4. **Judge**: field-by-field verdict per claim, with evidence.
5. **Reverse reconcile**: any write left over is an unclaimed write.
6. **Policy**: appointments the agent placed are checked against clinic rules.
7. **Seal** the report.

No language model is involved in steps 2-7. Verdicts are deterministic.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from subpoena import __version__
from subpoena.auditor import appointments, sidefx
from subpoena.auditor.context import AuditContext, Match
from subpoena.auditor.delta import SOURCE, Attribution
from subpoena.auditor.extractor import ClaimExtractor, RuleBasedExtractor, merge_claims
from subpoena.auditor.findings import DEFAULT_POLICIES, Policy, policy_violations, unclaimed_writes
from subpoena.auditor.seal import GENESIS, Sealer
from subpoena.auditor.verdicts import unverifiable
from subpoena.models import (
    AuditReport,
    AuditStats,
    CallRecord,
    Check,
    CheckName,
    Claim,
    ClaimSource,
    Entity,
    Finding,
    Outcome,
    Severity,
    Verdict,
    VerdictStatus,
    max_severity,
)
from subpoena.sor.base import AdapterUnavailable, SystemOfRecordReader
from subpoena.util import ClinicConfig, utcnow


@dataclass(frozen=True)
class _Handler:
    needs: tuple[Entity, ...]  # systems that must be readable to judge the claim
    consumes: Entity  # where the write that backs the claim lives
    match: Callable[[Any, AuditContext, bool], Match | None]
    judge: Callable[[Any, Match | None, AuditContext], Verdict]


_CALENDAR = (Entity.APPOINTMENT, Entity.PATIENT)
HANDLERS: dict[str, _Handler] = {
    "AppointmentBooked": _Handler(
        _CALENDAR, Entity.APPOINTMENT, appointments.match_booked, appointments.judge_booked
    ),
    "Rescheduled": _Handler(
        _CALENDAR,
        Entity.APPOINTMENT,
        appointments.match_rescheduled,
        appointments.judge_rescheduled,
    ),
    "Cancelled": _Handler(
        _CALENDAR, Entity.APPOINTMENT, appointments.match_cancelled, appointments.judge_cancelled
    ),
    "ConfirmationSent": _Handler(
        (Entity.MESSAGE,), Entity.MESSAGE, sidefx.match_confirmation, sidefx.judge_confirmation
    ),
    "HandoffCreated": _Handler(
        (Entity.TICKET, Entity.PATIENT), Entity.TICKET, sidefx.match_handoff, sidefx.judge_handoff
    ),
}


class Auditor:
    NAME = f"subpoena/{__version__}"

    def __init__(
        self,
        sor: SystemOfRecordReader,
        *,
        clinic: ClinicConfig | None = None,
        extractor: ClaimExtractor | None = None,
        use_transcript: bool = True,
        policies: Sequence[Policy] = DEFAULT_POLICIES,
        sealer: Sealer | None = None,
        clock: Callable[[], datetime] = utcnow,
        grace: timedelta = timedelta(seconds=30),
    ) -> None:
        self._sor = sor
        self._clinic = clinic or ClinicConfig()
        self._extractor = (extractor or RuleBasedExtractor()) if use_transcript else None
        self._policies = tuple(policies)
        self._sealer = sealer or Sealer()
        self._clock = clock
        self._grace = grace

    def audit(
        self, call: CallRecord, *, audit_id: str | None = None, prev_hash: str = GENESIS
    ) -> AuditReport:
        ctx = AuditContext.open(call, self._sor, self._clinic, self._grace)
        claims = self._collect_claims(call, ctx)
        matches, blocked = self._reconcile(claims, ctx)
        verdicts = tuple(self._judge(c, matches.get(c.claim_id), blocked, ctx) for c in claims)
        findings = self._findings(ctx, claims, verdicts)
        outcome = _outcome(verdicts, findings, ctx)
        ctx.log("verdict", f"Outcome: {outcome.value}")
        report = AuditReport(
            audit_id=audit_id or f"aud_{uuid.uuid4().hex[:12]}",
            auditor=self.NAME,
            created_at=self._clock(),
            call=call,
            outcome=outcome,
            verdicts=verdicts,
            findings=findings,
            trail=tuple(ctx.trail),
            stats=_stats(verdicts, findings),
        )
        return self._sealer.seal(report, prev_hash)

    # -- pipeline stages ---------------------------------------------------- #

    def _collect_claims(self, call: CallRecord, ctx: AuditContext) -> tuple[Claim, ...]:
        spoken = self._extractor.extract(call, self._clinic) if self._extractor else []
        claims = merge_claims(call.claims, spoken)
        spoken_only = [c for c in claims if c.source is ClaimSource.TRANSCRIPT]
        ctx.log(
            "claims",
            f"{len(call.claims)} structured claim(s); {len(spoken)} recovered from the "
            f"transcript, {len(spoken_only)} of them never logged by the agent",
        )
        return claims

    @staticmethod
    def _specificity(claim: Claim) -> int:
        """How much a claim says. A more specific claim has more ways to be wrong,
        so it must pin its evidence before a vaguer claim takes it."""
        skip = {"claim_id", "turn_index", "source", "utterance", "type"}
        return sum(1 for f, v in claim.model_dump().items() if f not in skip and v is not None)

    def _reconcile(
        self, claims: Sequence[Claim], ctx: AuditContext
    ) -> tuple[dict[str, Match], dict[str, str]]:
        """Pair claims with writes: exact matches claim their evidence first, and
        within a pass the most specific claims go first so a vague claim cannot
        take the write a specific one describes."""
        matches: dict[str, Match] = {}
        blocked: dict[str, str] = {}
        by_specificity = sorted(claims, key=self._specificity, reverse=True)
        for strict in (True, False):
            for claim in by_specificity:
                if claim.claim_id in matches or claim.claim_id in blocked:
                    continue
                handler = HANDLERS[claim.type]
                down = [SOURCE[e] for e in handler.needs if ctx.delta.get(e) is None]
                if down:
                    blocked[claim.claim_id] = f"{', '.join(down)} could not be read"
                    continue
                try:
                    match = handler.match(claim, ctx, strict)
                except AdapterUnavailable as exc:
                    blocked[claim.claim_id] = str(exc)
                    continue
                if match is not None:
                    matches[claim.claim_id] = match
                    ctx.consume(match)
                    refs = ", ".join(nc.entity_id for nc in match.changes)
                    kind = "exact" if strict else "partial"
                    ctx.log("reconcile", f"{claim.claim_id} ({claim.type}): {kind} match -> {refs}")
        for claim in claims:
            if claim.claim_id not in matches and claim.claim_id not in blocked:
                ctx.log("reconcile", f"{claim.claim_id} ({claim.type}): no write corresponds")
        return matches, blocked

    @staticmethod
    def _judge(
        claim: Claim, match: Match | None, blocked: dict[str, str], ctx: AuditContext
    ) -> Verdict:
        if claim.claim_id in blocked:
            verdict = unverifiable(claim, blocked[claim.claim_id])
        elif (ambiguous := ctx.ambiguous_identity(getattr(claim, "patient", None))) is not None:
            verdict = Verdict(
                claim=claim,
                status=VerdictStatus.UNVERIFIABLE,
                severity=Severity.HIGH,
                summary=f"Could not be checked: {ambiguous}. A guess here could clear a "
                "booking made for the wrong person.",
                checks=(Check(name=CheckName.EXISTENCE, passed=None, detail=ambiguous),),
                remediation="Disambiguate the patient (confirm the phone number on file) "
                "and re-run the audit.",
            )
        else:
            try:
                verdict = HANDLERS[claim.type].judge(claim, match, ctx)
            except AdapterUnavailable as exc:
                verdict = unverifiable(claim, str(exc))
            else:
                verdict = _apply_attribution(claim, verdict, match, ctx)
        ctx.log("verdict", f"{claim.claim_id} ({claim.type}): {verdict.status.value}")
        return verdict

    def _findings(
        self, ctx: AuditContext, claims: Sequence[Claim], verdicts: Sequence[Verdict]
    ) -> tuple[Finding, ...]:
        # A write can only be called "unclaimed" if every claim that might own it was
        # actually checked. An outage must never manufacture an accusation.
        unsound = {
            HANDLERS[v.claim.type].consumes
            for v in verdicts
            if v.status is VerdictStatus.UNVERIFIABLE
        }
        for entity in sorted(unsound):
            ctx.log(
                "reconcile",
                f"{SOURCE[entity]}: unclaimed-write check skipped, a claim that may own "
                "these writes could not be verified",
            )
        found = unclaimed_writes(ctx, claims, skip=frozenset(unsound))
        try:
            found += policy_violations(ctx, self._policies)
        except AdapterUnavailable as exc:
            ctx.log("policy", f"Policy checks skipped: {exc}")
        return tuple(
            f.model_copy(update={"finding_id": f"{ctx.call.call_id}-f{i}"})
            for i, f in enumerate(found, start=1)
        )


def _apply_attribution(
    claim: Claim, verdict: Verdict, match: Match | None, ctx: AuditContext
) -> Verdict:
    """Every matched verdict carries its attribution strength; an ambiguous one
    never stands as VERIFIED or MISMATCH.

    A write correlated by shared agent identity plus time window does not show
    *this* call made it once another call was in progress. The write is preserved
    as evidence, but the verdict is UNVERIFIABLE: the promised outcome may exist,
    yet which call caused it cannot be established.
    """
    if match is None or not match.changes:
        return verdict
    strength = ctx.match_attribution(match)
    if strength is Attribution.DIRECT:
        note = "Every backing write carries this call's own stamp."
    elif strength is Attribution.SOLE:
        note = (
            "Attributed by shared agent identity and time window; no concurrent call "
            "was observed in the journal."
        )
    else:
        note = (
            "Only shared agent identity plus an overlapping window links this write to "
            "the call, and another call was in progress - which call wrote it cannot "
            "be established."
        )
    check = Check(
        name=CheckName.ATTRIBUTION,
        passed=strength is not Attribution.AMBIGUOUS,
        detail=note,
    )
    if strength is not Attribution.AMBIGUOUS:
        return verdict.model_copy(update={"checks": verdict.checks + (check,)})
    if verdict.status not in (VerdictStatus.VERIFIED, VerdictStatus.MISMATCH):
        return verdict.model_copy(update={"checks": verdict.checks + (check,)})
    return Verdict(
        claim=claim,
        status=VerdictStatus.UNVERIFIABLE,
        severity=Severity.HIGH,
        summary=(
            "A write matching this claim exists, but it is attributed only to the shared "
            "agent identity while another call was in progress. The promised outcome may "
            "exist; that this call caused it cannot be proven."
        ),
        checks=verdict.checks + (check,),
        diffs=verdict.diffs,
        evidence=verdict.evidence,
        remediation=(
            "Re-run the audit once the calls no longer overlap, or have the platform "
            "stamp writes with the call id so attribution is direct."
        ),
    )


def _outcome(
    verdicts: Sequence[Verdict], findings: Sequence[Finding], ctx: AuditContext
) -> Outcome:
    flagged = {VerdictStatus.MISMATCH, VerdictStatus.NOT_FOUND}
    if findings or any(v.status in flagged for v in verdicts):
        return Outcome.DISCREPANCIES
    blind = any(d is None for d in ctx.delta.values())
    if blind or any(v.status is VerdictStatus.UNVERIFIABLE for v in verdicts):
        return Outcome.INCONCLUSIVE  # an unreadable system can hide unclaimed writes
    return Outcome.CLEAN


def _stats(verdicts: Sequence[Verdict], findings: Sequence[Finding]) -> AuditStats:
    count = {s: sum(v.status is s for v in verdicts) for s in VerdictStatus}
    checkable = len(verdicts) - count[VerdictStatus.UNVERIFIABLE]
    return AuditStats(
        claims=len(verdicts),
        verified=count[VerdictStatus.VERIFIED],
        mismatch=count[VerdictStatus.MISMATCH],
        not_found=count[VerdictStatus.NOT_FOUND],
        unverifiable=count[VerdictStatus.UNVERIFIABLE],
        findings=len(findings),
        trust_score=round(count[VerdictStatus.VERIFIED] / checkable, 3) if checkable else None,
        max_severity=max_severity([v.severity for v in verdicts] + [f.severity for f in findings]),
    )
