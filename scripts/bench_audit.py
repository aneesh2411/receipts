#!/usr/bin/env python3
"""Benchmark the in-memory audit pipeline: python scripts/bench_audit.py -n 1000 --check.

Synthetic call generation is untimed. Ingest covers saving and loading a call,
audit covers extraction and reconciliation, and seal covers signing and ledger
insertion. Claims/sec uses the sum of these three elapsed times.
"""

from __future__ import annotations

import argparse
import random
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field, replace
from time import perf_counter_ns

from subpoena.api.store import AuditStore
from subpoena.auditor.seal import GENESIS, Sealer
from subpoena.models import AuditReport, VerdictStatus
from subpoena.scenarios import GOLDEN, audit_call, build_world, run_suspect

SEED = 81
SCENARIOS = tuple(scenario for scenario in GOLDEN if not scenario.known_gap)


class DeferredSealer(Sealer):
    """Leave sealing to the ledger append via Auditor's public sealer argument."""

    def seal(self, report: AuditReport, prev_hash: str = GENESIS) -> AuditReport:
        return report


@dataclass
class BenchmarkResult:
    ingest_ns: int = 0
    audit_ns: int = 0
    seal_ns: int = 0
    calls_ingested: int = 0
    calls_audited: int = 0
    structured_claims: int = 0
    peak_claims: int = 0
    verdicts: Counter[VerdictStatus] = field(default_factory=Counter)

    def table(self) -> str:
        claims = self.verdicts.total()
        elapsed = (self.ingest_ns + self.audit_ns + self.seal_ns) / 1e9
        rate = f"{claims / elapsed:,.1f}" if elapsed else "n/a"
        rows = [
            ("Calls ingested", self.calls_ingested),
            ("Calls audited", self.calls_audited),
            ("Structured claims ingested", self.structured_claims),
            ("Claims audited", claims),
            ("Peak audited claims per call", self.peak_claims),
            *((status.value, self.verdicts[status]) for status in VerdictStatus),
            ("Ingest (ms)", f"{self.ingest_ns / 1e6:.3f}"),
            ("Audit (ms)", f"{self.audit_ns / 1e6:.3f}"),
            ("Seal and append (ms)", f"{self.seal_ns / 1e6:.3f}"),
            ("Claims/sec", rate),
        ]
        return "\n".join(
            ["| Metric | Value |", "| --- | ---: |"]
            + [f"| {label} | {value} |" for label, value in rows]
        )


def benchmark(calls: int, *, check: bool = False) -> BenchmarkResult:
    rng = random.Random(SEED)
    stats = BenchmarkResult()
    expected: Counter[VerdictStatus] = Counter()
    deferred_sealer, sealer = DeferredSealer(), Sealer(b"subpoena-audit-benchmark")

    with closing(AuditStore()) as ledger:
        for index in range(calls):
            template = rng.choice(SCENARIOS)
            scenario = replace(template, id=f"{template.id}-bench-{index}")
            world = build_world(scenario)
            with closing(world.store):
                simulated = run_suspect(scenario, world)
                started = perf_counter_ns()
                saved = ledger.save_call(simulated.call)
                stored = ledger.get_call(simulated.call.call_id)
                stats.ingest_ns += perf_counter_ns() - started
                if not saved or stored is None:
                    raise RuntimeError(f"Ingest failed for {simulated.call.call_id}")
                stats.calls_ingested += 1
                stats.structured_claims += len(stored.claims)
                ingested = replace(simulated, call=stored)

                started = perf_counter_ns()
                report = audit_call(scenario, world, ingested, sealer=deferred_sealer)
                stats.audit_ns += perf_counter_ns() - started

                started = perf_counter_ns()
                sealed = ledger.append(report, sealer)
                stats.seal_ns += perf_counter_ns() - started

            stats.calls_audited += 1
            stats.peak_claims = max(stats.peak_claims, len(sealed.verdicts))
            stats.verdicts.update(verdict.status for verdict in sealed.verdicts)
            if check:
                expected.update(status for _, status in template.expected_claims)
                if sealed.call.call_id != simulated.call.call_id:
                    raise AssertionError(f"Missing audit for {simulated.call.call_id}")
                if len(sealed.verdicts) != len(template.expected_claims):
                    raise AssertionError(
                        f"{simulated.call.call_id}: expected {len(template.expected_claims)} "
                        f"audited claims, got {len(sealed.verdicts)}"
                    )

    if check:
        if stats.calls_ingested != calls or stats.calls_audited != calls:
            raise AssertionError(
                f"Expected {calls} calls, ingested {stats.calls_ingested}, "
                f"audited {stats.calls_audited}"
            )
        if stats.verdicts != expected:
            raise AssertionError(f"Expected verdicts {dict(expected)}, got {dict(stats.verdicts)}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark seeded synthetic call audits.")
    parser.add_argument("-n", "--calls", type=int, default=1000, help="number of synthetic calls")
    parser.add_argument(
        "--check", action="store_true", help="verify counts and verdict distribution"
    )
    args = parser.parse_args()
    if args.calls < 1:
        parser.error("--calls must be positive")
    print(benchmark(args.calls, check=args.check).table())


if __name__ == "__main__":
    main()
