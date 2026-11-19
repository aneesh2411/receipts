"""Exercise the benchmark without making assumptions about throughput."""

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import bench_audit
from subpoena.models import VerdictStatus

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bench_audit.py"


def test_checked_benchmark_is_independent_of_elapsed_time(monkeypatch):
    first = bench_audit.benchmark(100, check=True)
    monkeypatch.setattr(bench_audit, "perf_counter_ns", lambda: 0)
    second = bench_audit.benchmark(100, check=True)

    assert second == replace(first, ingest_ns=0, audit_ns=0, seal_ns=0)
    assert second.calls_ingested == second.calls_audited == 100
    assert all(second.verdicts[status] > 0 for status in VerdictStatus)
    assert "| Claims/sec | n/a |" in second.table()


@pytest.mark.parametrize("drop_claim", [True, False])
def test_check_rejects_incorrect_verdicts(monkeypatch, drop_claim):
    append = bench_audit.AuditStore.append

    def append_with_bad_verdict(store, report, sealer):
        if report.verdicts:
            first, *rest = report.verdicts
            if not drop_claim:
                other_status = next(status for status in VerdictStatus if status != first.status)
                rest.insert(0, first.model_copy(update={"status": other_status}))
            report = report.model_copy(update={"verdicts": tuple(rest)})
        return append(store, report, sealer)

    monkeypatch.setattr(bench_audit.AuditStore, "append", append_with_bad_verdict)
    message = "audited claims" if drop_claim else "Expected verdicts"
    with pytest.raises(AssertionError, match=message):
        bench_audit.benchmark(1, check=True)


def test_cli_prints_markdown_table():
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--calls", "5", "--check"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.startswith("| Metric | Value |\n| --- | ---: |\n")
    assert "| Calls audited | 5 |" in run.stdout
    for metric in ("Ingest (ms)", "Audit (ms)", "Seal and append (ms)", "Claims/sec"):
        assert f"| {metric} |" in run.stdout
