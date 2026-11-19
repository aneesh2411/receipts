#!/usr/bin/env python3
"""Verify standalone sealed audit exports offline.

The seal covers the whole report, including the order of its receipts (claim
verdicts). A failed seal identifies the affected report. Provide a signing key
to require HMAC authentication in addition to integrity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from subpoena.auditor.seal import GENESIS, Integrity, Sealer, canonical_bytes
from subpoena.models import AuditReport


def verify_file(path: Path, sealer: Sealer) -> bool:
    report_id = str(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("audit_id"), str):
            report_id = payload["audit_id"]
        report = AuditReport.model_validate(payload)
        check = sealer.verify(report, expected_prev=GENESIS)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Report {report_id!r} FAILED ({type(exc).__name__}: {str(exc).splitlines()[0]})")
        return False

    integrity, authentication, reason = check.integrity, check.authentication, check.reason
    # Model validation can restore omitted defaults or coerce edited values.
    # Check the exported payload before accepting the re-canonicalized report.
    exported_content = {name: value for name, value in payload.items() if name != "seal"}
    if exported_content != json.loads(canonical_bytes(report)):
        integrity = Integrity.ALTERED
        reason = "exported content differs from the canonical report"

    print(
        f"Report {report_id!r} receipts={len(report.verdicts)} "
        f"integrity={integrity} authentication={authentication} ({reason})"
    )
    return check.ok and integrity is Integrity.INTACT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("reports", type=Path, nargs="+", help="standalone audit JSON files")
    parser.add_argument("--key", help="UTF-8 signing key (omit to check integrity only)")
    args = parser.parse_args()
    if args.key == "":
        parser.error("--key must be non-empty")

    sealer = Sealer(args.key.encode("utf-8") if args.key is not None else None)
    passed = sum(verify_file(path, sealer) for path in args.reports)
    total = len(args.reports)
    verdict = "PASS" if passed == total else "FAIL"
    print(f"VERDICT {verdict} (whole-report verification, {passed}/{total} reports passed)")
    return int(passed != total)


if __name__ == "__main__":
    raise SystemExit(main())
