#!/usr/bin/env python3
"""Compare the claim verdicts and field values of two sealed audit exports."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from subpoena.auditor.seal import GENESIS, Sealer, canonical_bytes
from subpoena.models import AuditReport, Verdict


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _verify(path: Path, sealer: Sealer) -> tuple[AuditReport | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        report = AuditReport.model_validate(payload)
        check = sealer.verify(report, expected_prev=GENESIS)
        # Validation may coerce values or restore defaults before hashing.
        exported = {name: value for name, value in payload.items() if name != "seal"}
        if _json(exported).encode() != canonical_bytes(report):
            return None, (
                f"FAILED integrity=altered authentication={check.authentication} "
                "(exported content differs from the canonical report)"
            )
    except (OSError, ValueError, TypeError) as exc:
        return None, f"FAILED ({str(exc).splitlines()[0]})"

    status = f"integrity={check.integrity} authentication={check.authentication} ({check.reason})"
    if not check.ok:
        return None, f"FAILED {status}"
    return report, f"OK {status}"


def _index(report: AuditReport) -> dict[str, Verdict]:
    verdicts = {}
    for verdict in report.verdicts:
        claim_id = verdict.claim.claim_id
        if claim_id in verdicts:
            raise ValueError(f"report {report.audit_id!r} has duplicate claim ID {_json(claim_id)}")
        verdicts[claim_id] = verdict
    return verdicts


def _field_rows(verdict: Verdict) -> dict[str, list[dict[str, Any]]]:
    rows = defaultdict(list)
    for diff in verdict.diffs:
        rows[diff.field].append(diff.model_dump(mode="json", exclude={"field"}))
    return rows


def _field_changes(label: str, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes = []
    for field in sorted(before.keys() | after.keys()):
        old = _json(before[field]) if field in before else "(absent)"
        new = _json(after[field]) if field in after else "(absent)"
        if old != new:
            changes.append(f"  {label} {_json(field)}: {old} -> {new}")
    return changes


def _diff(before: AuditReport, after: AuditReport) -> list[str]:
    old_verdicts, new_verdicts = _index(before), _index(after)
    lines = []
    if before.call.call_id != after.call.call_id:
        lines.append(f"WARNING: CALL ID MISMATCH: {before.call.call_id} -> {after.call.call_id}")

    changes = []
    for claim_id in sorted(old_verdicts.keys() | new_verdicts.keys()):
        old, new = old_verdicts.get(claim_id), new_verdicts.get(claim_id)
        name = f"Claim {_json(claim_id)}"
        if old is None:
            changes.append(f"ADDED {name} ({new.status})")
        elif new is None:
            changes.append(f"REMOVED {name} ({old.status})")
        else:
            details = []
            if old.status != new.status:
                details.append(f"  Verdict: {old.status} -> {new.status}")
            details.extend(
                _field_changes(
                    "Claim field",
                    old.claim.model_dump(mode="json", exclude={"claim_id"}),
                    new.claim.model_dump(mode="json", exclude={"claim_id"}),
                )
            )
            details.extend(_field_changes("Receipt field", _field_rows(old), _field_rows(new)))
            if details:
                changes.extend([f"{name}:", *details])
    return lines + (changes or ["No claim changes."])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="before audit JSON")
    parser.add_argument("after", type=Path, help="after audit JSON")
    parser.add_argument("--key", help="UTF-8 signing key (omit to check integrity only)")
    args = parser.parse_args()
    if args.key == "":
        parser.error("--key must be non-empty")

    sealer = Sealer(args.key.encode("utf-8") if args.key is not None else None)
    before, before_status = _verify(args.before, sealer)
    after, after_status = _verify(args.after, sealer)
    statuses = [f"Before seal: {before_status}", f"After seal: {after_status}"]
    if before is None or after is None:
        print(*statuses, "Diff refused: both seals must verify.", sep="\n", file=sys.stderr)
        return 1

    try:
        changes = _diff(before, after)
    except ValueError as exc:
        print(*statuses, f"Diff refused: {exc}", sep="\n", file=sys.stderr)
        return 1

    print(*statuses, *changes, sep="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
