#!/usr/bin/env python3
"""Generate a golden scenario skeleton from a finding in a sealed audit export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from pprint import pformat

from subpoena.auditor.seal import GENESIS, Sealer, canonical_bytes
from subpoena.models import AuditReport, Evidence


def load_report(path: Path, sealer: Sealer) -> AuditReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = AuditReport.model_validate(payload)
    check = sealer.verify(report, expected_prev=GENESIS)
    if not check.ok:
        raise ValueError(f"audit seal verification failed: {check.reason}")

    # Validation can restore omitted defaults and coerce edited values.
    exported_content = {name: value for name, value in payload.items() if name != "seal"}
    if json.dumps(exported_content, sort_keys=True, separators=(",", ":")).encode() != (
        canonical_bytes(report)
    ):
        raise ValueError("audit seal verification failed: export differs from the sealed content")
    return report


def missing_snapshots(label: str, evidence: tuple[Evidence, ...]) -> list[str]:
    if not evidence:
        return [f"{label} has no system-of-record snapshot in the export."]
    return [
        f"{label} has no system-of-record snapshot for {entry.source!a}/{entry.ref!a}."
        for entry in evidence
        if entry.record is None
    ]


def render_scenario(report: AuditReport, finding_id: str) -> tuple[str, list[str]]:
    matches = [finding for finding in report.findings if finding.finding_id == finding_id]
    if not matches:
        raise ValueError(f"unknown finding id {finding_id!a} in audit {report.audit_id!a}")
    if len(matches) != 1:
        raise ValueError(f"ambiguous finding id {finding_id!a} in audit {report.audit_id!a}")
    finding = matches[0]
    assert report.seal is not None

    missing = missing_snapshots(f"Finding {finding_id!a}", finding.evidence)
    for verdict in report.verdicts:
        missing.extend(missing_snapshots(f"Claim {verdict.claim.claim_id!a}", verdict.evidence))

    header = [
        "# Golden scenario skeleton",
        f"# Source audit ID: {report.audit_id!a}",
        f"# Receipt hash (seal.content_hash): {report.seal.content_hash}",
        f"# Audit chain hash (seal.chain_hash): {report.seal.chain_hash}",
        f"# Source finding ID: {finding_id!a}",
    ]
    header.extend(f"# TODO: {message}" for message in missing)
    header.extend(
        [
            "# TODO: Supply simulator steps, starting state, and fault settings.",
            "# The snapshots below describe observed evidence from the call.",
        ]
    )

    sections = [
        "\n".join(header),
        """from collections.abc import Mapping

from subpoena.models import PatientRef, VerdictStatus
from subpoena.scenarios.world import Scenario, SeedAppointment
from subpoena.suspect import FaultMode, Step""",
        f"CALL = {pformat(report.call.model_dump(mode='json'))}",
        f"FINDING = {pformat(finding.model_dump(mode='json'))}",
        f"VERDICTS = {pformat([verdict.model_dump(mode='json') for verdict in report.verdicts])}",
        f"EXPECTED_OUTCOME = {report.outcome.value!r}",
        """def build_scenario(
    *,
    steps: tuple[Step, ...],
    seed: tuple[SeedAppointment, ...],
    faults: Mapping[int, frozenset[FaultMode]],
    **scenario_options,
) -> Scenario:
    return Scenario(
        id=FINDING["finding_id"],
        title=FINDING["code"],
        story=FINDING["summary"],
        caller=PatientRef.model_validate(CALL["caller"]),
        steps=steps,
        seed=seed,
        faults=faults,
        expected_claims=tuple(
            (verdict["claim"]["type"], VerdictStatus(verdict["status"]))
            for verdict in VERDICTS
        ),
        expected_findings=(FINDING["code"],),
        **scenario_options,
    )""",
    ]
    return "\n\n\n".join(sections) + "\n", missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path, help="standalone sealed audit JSON")
    parser.add_argument("finding_id", help="finding_id from the audit's findings array")
    parser.add_argument("-o", "--output", type=Path, help="new Python file (default: stdout)")
    parser.add_argument("--key", help="UTF-8 signing key (omit to check integrity only)")
    args = parser.parse_args()
    if args.key == "":
        parser.error("--key must be non-empty")

    try:
        report = load_report(
            args.audit, Sealer(args.key.encode() if args.key is not None else None)
        )
        source, missing = render_scenario(report, args.finding_id)
        if args.output is None:
            sys.stdout.write(source)
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(source)
    except (OSError, ValueError) as exc:
        print(f"error: {str(exc).splitlines()[0]}", file=sys.stderr)
        return 1

    for message in missing:
        print(f"TODO: {message}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
