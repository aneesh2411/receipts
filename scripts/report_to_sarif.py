#!/usr/bin/env python3
"""Convert a Subpoena audit report to SARIF 2.1.0. By default, the seal is not verified."""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from subpoena.auditor.seal import GENESIS, Sealer, canonical_bytes
from subpoena.models import AuditReport, Severity, VerdictStatus

LEVELS = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}
RULES = {
    VerdictStatus.MISMATCH: "The action differed from the claim.",
    VerdictStatus.NOT_FOUND: "No evidence of the claimed action was found.",
    VerdictStatus.UNVERIFIABLE: "The evidence source could not be read.",
}


def to_sarif(report: AuditReport) -> dict:
    results = []
    for verdict in report.verdicts:
        if verdict.status is VerdictStatus.VERIFIED:
            continue

        rule_id = f"subpoena/{verdict.status}"
        identity = json.dumps(
            [report.call.agent_id, report.call.call_id, verdict.claim.claim_id, rule_id]
        )
        message = verdict.summary
        if verdict.remediation:
            message += f"\n\nRemediation: {verdict.remediation}"

        results.append(
            {
                "ruleId": rule_id,
                "level": LEVELS[verdict.severity],
                "message": {"text": message},
                "partialFingerprints": {
                    "subpoena/v1": sha256(identity.encode("utf-8")).hexdigest()
                },
            }
        )

    rules = [
        {"id": f"subpoena/{status}", "shortDescription": {"text": description}}
        for status, description in RULES.items()
    ]
    return {
        "$schema": "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.5.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "Subpoena", "rules": rules}}, "results": results}],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("-o", type=Path, help="write SARIF to this file")
    parser.add_argument(
        "--verify", action="store_true", help="require an intact standalone report seal"
    )
    args = parser.parse_args()

    try:
        data = args.report_json.read_bytes()
        report = AuditReport.model_validate_json(data)
    except OSError as exc:
        parser.exit(1, f"Unable to read report {args.report_json}: {exc}\n")
    except ValidationError as exc:
        parser.exit(1, f"Invalid audit report {args.report_json}: {exc}\n")

    if args.verify:
        try:
            check = Sealer().verify(report, expected_prev=GENESIS)
            if not check.ok:
                raise ValueError(check.reason)

            # Model validation can restore omitted defaults or coerce edited values.
            payload = json.loads(data)
            payload.pop("seal")
            exported_content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            if exported_content != canonical_bytes(report):
                raise ValueError("exported content differs from the canonical report")
        except (ValueError, RecursionError) as exc:
            parser.exit(1, f"Seal verification failed for {args.report_json}: {exc}\n")

    output = json.dumps(to_sarif(report), indent=2, sort_keys=True) + "\n"
    try:
        if args.o is None:
            sys.stdout.write(output)
        else:
            args.o.write_text(output, encoding="utf-8", newline="\n")
    except OSError as exc:
        parser.exit(1, f"Unable to write SARIF: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
