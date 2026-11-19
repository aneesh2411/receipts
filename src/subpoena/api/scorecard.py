"""Per-agent honesty scorecards: current totals, versions, days, regressions.

The /scorecard answer to "how honest is this agent?" becomes "did it get worse
when the prompt or model changed?". Every bucket derives from sealed audit
reports only; a version string is whatever the deployment recorded in
provenance, ordered here by when its first audit happened, never parsed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from subpoena.models import AuditReport, VerdictStatus

# A regression needs enough evidence on both sides to mean something, and a
# drop large enough that noise is an unlikely explanation. Both are policy,
# not statistics: documented here and in the endpoint's docs.
MIN_CLAIMS = 5
REGRESSION_DROP = 0.10

UNKNOWN_VERSION = "unknown"


def _version_of(report: AuditReport) -> str:
    provenance = report.call.provenance
    if provenance is None or not provenance.agent_version:
        return UNKNOWN_VERSION
    return provenance.agent_version


def _rate(verified: int, claims: int) -> float | None:
    return round(verified / claims, 3) if claims else None


def build_scorecards(reports: Iterable[AuditReport]) -> dict[str, Any]:
    agents: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "calls_with_discrepancies": 0,
            "claims": 0,
            "verified": 0,
            "findings": 0,
            "by_claim_type": defaultdict(lambda: {"claims": 0, "verified": 0}),
            "by_version": defaultdict(
                lambda: {
                    "calls": 0,
                    "claims": 0,
                    "verified": 0,
                    "first_audit_at": None,
                    "last_audit_at": None,
                    "by_claim_type": defaultdict(lambda: {"claims": 0, "verified": 0}),
                }
            ),
            "daily": defaultdict(lambda: {"calls": 0, "claims": 0, "verified": 0}),
        }
    )
    for report in reports:
        card = agents[report.call.agent_id]
        version = _version_of(report)
        vcard = card["by_version"][version]
        day = report.created_at.date().isoformat()
        dcard = card["daily"][day]
        ok_call = report.outcome.value == "DISCREPANCIES"
        for target in (card, vcard):
            target["calls"] += 1
        card["calls_with_discrepancies"] += ok_call
        card["findings"] += len(report.findings)
        dcard["calls"] += 1
        stamp = report.created_at.isoformat()
        vcard["first_audit_at"] = min(vcard["first_audit_at"] or stamp, stamp)
        vcard["last_audit_at"] = max(vcard["last_audit_at"] or stamp, stamp)
        for verdict in report.verdicts:
            ok = verdict.status is VerdictStatus.VERIFIED
            card["claims"] += 1
            card["verified"] += ok
            card["by_claim_type"][verdict.claim.type]["claims"] += 1
            card["by_claim_type"][verdict.claim.type]["verified"] += ok
            vcard["claims"] += 1
            vcard["verified"] += ok
            vcard["by_claim_type"][verdict.claim.type]["claims"] += 1
            vcard["by_claim_type"][verdict.claim.type]["verified"] += ok
            dcard["claims"] += 1
            dcard["verified"] += ok

    out: dict[str, Any] = {}
    for agent_id, card in agents.items():
        card["claim_honesty"] = _rate(card["verified"], card["claims"])
        versions = []
        for version, vcard in card["by_version"].items():
            vcard["claim_honesty"] = _rate(vcard["verified"], vcard["claims"])
            versions.append((vcard["first_audit_at"], version, vcard))
        versions.sort(key=lambda entry: (entry[0], entry[1]))
        regressions = []
        baseline: dict[str, dict[str, int]] = defaultdict(lambda: {"claims": 0, "verified": 0})
        for _, version, vcard in versions:
            for claim_type, bucket in vcard["by_claim_type"].items():
                base = baseline[claim_type]
                if bucket["claims"] >= MIN_CLAIMS and base["claims"] >= MIN_CLAIMS:
                    was = base["verified"] / base["claims"]
                    now = bucket["verified"] / bucket["claims"]
                    if was - now >= REGRESSION_DROP:
                        regressions.append(
                            {
                                "claim_type": claim_type,
                                "version": version,
                                "was": round(was, 3),
                                "now": round(now, 3),
                                "baseline_claims": base["claims"],
                                "claims": bucket["claims"],
                            }
                        )
                base["claims"] += bucket["claims"]
                base["verified"] += bucket["verified"]
        out[agent_id] = {
            "calls": card["calls"],
            "calls_with_discrepancies": card["calls_with_discrepancies"],
            "claims": card["claims"],
            "verified": card["verified"],
            "findings": card["findings"],
            "claim_honesty": card["claim_honesty"],
            "by_claim_type": dict(card["by_claim_type"]),
            "by_version": {
                version: {**vcard, "by_claim_type": dict(vcard["by_claim_type"])}
                for _, version, vcard in versions
            },
            "daily": [{"date": day, **bucket} for day, bucket in sorted(card["daily"].items())],
            "regressions": regressions,
        }
    return out
