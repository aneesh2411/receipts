#!/usr/bin/env python3
"""Summarize standalone sealed audit reports offline."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from subpoena.auditor.seal import GENESIS, Sealer, canonical_bytes
from subpoena.models import AuditReport, Severity, VerdictStatus


def verified_report(path: Path, sealer: Sealer) -> AuditReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = AuditReport.model_validate(payload)
    check = sealer.verify(report, expected_prev=GENESIS)
    if not check.ok:
        raise ValueError(check.reason)

    # Like verify_seal.py, check the export before accepting values that model
    # validation may have coerced or restored from defaults.
    exported_content = {name: value for name, value in payload.items() if name != "seal"}
    if json.dumps(exported_content, sort_keys=True, separators=(",", ":")).encode() != (
        canonical_bytes(report)
    ):
        raise ValueError("exported content differs from the canonical report")
    return report


def summarize(directory: Path) -> tuple[str, int]:
    sealer = Sealer()
    total = 0
    verdicts: Counter[VerdictStatus] = Counter()
    codes: Counter[str] = Counter()
    severities: Counter[Severity] = Counter()
    failures = []

    for path in sorted(directory.iterdir(), key=lambda path: path.name):
        if path.suffix != ".json" or not path.is_file():
            continue
        try:
            report = verified_report(path, sealer)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            reason = str(exc).splitlines()[0]
            failures.append(f"- {path.name}: {reason}")
            continue
        total += 1
        verdicts.update(verdict.status for verdict in report.verdicts)
        codes.update(finding.code for finding in report.findings)
        severities.update(finding.severity for finding in report.findings)

    lines = ["# Audit summary", "", f"Total reports: {total}", "", "## Verdict statuses", ""]
    lines.extend(f"- {status}: {verdicts[status]}" for status in VerdictStatus)
    lines.extend(["", "## Finding codes", ""])
    lines.extend([f"- {code}: {codes[code]}" for code in sorted(codes)] or ["None."])
    lines.extend(["", "## Finding severities", ""])
    lines.extend(f"- {severity}: {severities[severity]}" for severity in Severity)
    lines.extend(["", "## Seal failures", ""])
    lines.extend(failures or ["None."])
    return "\n".join(lines) + "\n", int(bool(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory of standalone audit JSON files")
    parser.add_argument("-o", type=Path, metavar="OUT.md", help="write Markdown to this file")
    args = parser.parse_args()

    try:
        markdown, status = summarize(args.directory)
        if args.o is None:
            sys.stdout.write(markdown)
        else:
            args.o.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
