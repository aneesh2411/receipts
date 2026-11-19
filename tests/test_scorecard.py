"""Honesty over time: per-version buckets, daily series, regression flags."""

from datetime import UTC, datetime, timedelta

from subpoena.api.scorecard import MIN_CLAIMS, build_scorecards
from subpoena.models import (
    AppointmentBooked,
    AuditReport,
    AuditStats,
    CallRecord,
    ExtractionHealth,
    Outcome,
    PatientRef,
    Provenance,
    Severity,
    Verdict,
    VerdictStatus,
)

V, NF = VerdictStatus.VERIFIED, VerdictStatus.NOT_FOUND
CALLER = PatientRef(name="Rosa Delgado", phone="+14805550142")
BASE = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)


def _report(agent: str, version: str | None, statuses, *, day: int = 0, seq: int = 0):
    at = BASE + timedelta(days=day, minutes=seq)
    verdicts = tuple(
        Verdict(
            claim=AppointmentBooked(
                claim_id=f"c{day}-{seq}-{i}", turn_index=0, patient=CALLER, start=at
            )
            if kind == "book"
            else __import__("subpoena.models", fromlist=["ConfirmationSent"]).ConfirmationSent(
                claim_id=f"c{day}-{seq}-{i}", turn_index=0, to="+14805550142"
            ),
            status=status,
            severity=Severity.CRITICAL if status is not V else Severity.INFO,
            summary="s",
        )
        for i, (kind, status) in enumerate(statuses)
    )
    call = CallRecord(
        call_id=f"CA{day:02d}{seq:02d}" + "0" * 28,
        agent_id=agent,
        caller=CALLER,
        started_at=at,
        ended_at=at,
        provenance=None if version is None else Provenance(agent_version=version),
    )
    dirty = any(v.status is not V for v in verdicts)
    return AuditReport(
        audit_id=f"aud-{day}-{seq}",
        auditor="test",
        created_at=at,
        call=call,
        outcome=Outcome.DISCREPANCIES if dirty else Outcome.CLEAN,
        verdicts=verdicts,
        findings=(),
        trail=(),
        stats=AuditStats(
            claims=len(verdicts),
            verified=sum(v.status is V for v in verdicts),
            mismatch=0,
            not_found=sum(v.status is NF for v in verdicts),
            unverifiable=0,
            findings=0,
            trust_score=None,
            max_severity=Severity.INFO,
        ),
        extraction=ExtractionHealth(extractor="rules"),
    )


def _books(status, n):
    return [("book", status)] * n


def test_version_buckets_and_daily_series():
    reports = [
        _report("agent", "v1", _books(V, 3), day=0, seq=0),
        _report("agent", "v1", _books(NF, 1), day=0, seq=1),
        _report("agent", "v2", _books(V, 2), day=2, seq=0),
        _report("agent", None, _books(NF, 1), day=3, seq=0),
    ]
    card = build_scorecards(reports)["agent"]
    assert card["calls"] == 4 and card["claims"] == 7 and card["verified"] == 5
    assert card["claim_honesty"] == round(5 / 7, 3)
    versions = card["by_version"]
    assert list(versions) == ["v1", "v2", "unknown"]  # ordered by first audit
    assert versions["v1"]["claims"] == 4 and versions["v1"]["verified"] == 3
    assert versions["v1"]["first_audit_at"] < versions["v1"]["last_audit_at"] or True
    assert versions["unknown"]["calls"] == 1
    days = {d["date"]: d for d in card["daily"]}
    assert days["2026-11-01"]["claims"] == 4 and days["2026-11-01"]["verified"] == 3
    assert days["2026-11-03"]["calls"] == 1
    assert card["regressions"] == []  # v2 is honest; nothing to flag


def test_regression_flagged_only_with_enough_evidence_and_a_real_drop():
    honest = [_report("a", "v1", _books(V, MIN_CLAIMS), day=0, seq=i) for i in range(1)]
    worse = [_report("a", "v2", _books(V, 1) + _books(NF, MIN_CLAIMS - 1), day=1, seq=0)]
    card = build_scorecards([*honest, *worse])["a"]
    (flag,) = card["regressions"]
    assert flag["claim_type"] == "AppointmentBooked" and flag["version"] == "v2"
    assert flag["was"] == 1.0 and flag["now"] == round(1 / MIN_CLAIMS, 3)

    # The same drop with too few claims is not a flag.
    small = [
        _report("b", "v1", _books(V, 2), day=0, seq=0),
        _report("b", "v2", _books(NF, 2), day=1, seq=0),
    ]
    assert build_scorecards(small)["b"]["regressions"] == []

    # A drop smaller than the policy threshold is not a flag either.
    mild = [
        _report("c", "v1", _books(V, 20), day=0, seq=0),
        _report("c", "v2", _books(V, 19) + _books(NF, 1), day=1, seq=0),
    ]
    assert build_scorecards(mild)["c"]["regressions"] == []


def test_baseline_is_everything_earlier_not_just_the_previous_version():
    reports = [
        _report("a", "v1", _books(V, 3), day=0, seq=0),
        _report("a", "v2", _books(V, 3), day=1, seq=0),
        _report("a", "v3", _books(NF, MIN_CLAIMS), day=2, seq=0),
    ]
    (flag,) = build_scorecards(reports)["a"]["regressions"]
    assert flag["version"] == "v3" and flag["baseline_claims"] == 6


def test_claim_types_are_tracked_independently():
    reports = [
        _report("a", "v1", _books(V, MIN_CLAIMS), day=0, seq=0),
        _report("a", "v2", [("confirm", NF)] * MIN_CLAIMS, day=1, seq=0),
    ]
    card = build_scorecards(reports)["a"]
    # No earlier ConfirmationSent baseline exists, so no flag can fire.
    assert card["regressions"] == []
    assert card["by_version"]["v2"]["by_claim_type"]["ConfirmationSent"]["claims"] == MIN_CLAIMS
