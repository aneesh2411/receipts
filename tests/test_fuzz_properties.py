"""Seeded, offline properties of the auditor's reconciliation results."""

import json
import os
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

from subpoena.evals.fuzz import generate
from subpoena.evals.score import claim_identity
from subpoena.models import AuditReport, VerdictStatus
from subpoena.scenarios.world import audit_call, build_world, run_scenario, run_suspect

CASE_COUNT = 200
SEED = 95
ABSENT_STATUSES = {VerdictStatus.NOT_FOUND, VerdictStatus.UNVERIFIABLE}


def test_absent_evidence_never_verifies():
    for scenario in generate(CASE_COUNT, SEED):
        statuses = defaultdict(deque)
        for verdict in run_scenario(scenario).report.verdicts:
            key = verdict.claim.type, claim_identity(verdict.claim)
            statuses[key].append(verdict.status)

        # Both sequences are in step order within each identity. Consume each
        # occurrence so two same-priority handoffs are checked separately.
        for kind, expected, identity in scenario.expected_claims_v2:
            queue = statuses[kind, identity]
            actual = queue.popleft() if queue else None
            if expected is VerdictStatus.NOT_FOUND:
                assert actual in ABSENT_STATUSES, (scenario.id, scenario.title, identity, actual)


def _verdicts(report: AuditReport):
    return [
        (verdict.claim.type, claim_identity(verdict.claim), verdict.status, verdict.severity)
        for verdict in report.verdicts
    ]


def _audit_twice():
    snapshots = {}
    for scenario in generate(CASE_COUNT, SEED):
        world = build_world(scenario)
        try:
            result = run_suspect(scenario, world)
            first = _verdicts(audit_call(scenario, world, result))
            second = _verdicts(audit_call(scenario, world, result))
            assert first == second, (scenario.id, scenario.title, first, second)
            snapshots[scenario.id] = first
        finally:
            world.store.close()
    return snapshots


def test_verdicts_are_deterministic():
    script = Path(__file__).resolve()
    snapshots = [
        json.loads(
            subprocess.check_output(
                [sys.executable, str(script)],
                env={**os.environ, "PYTHONHASHSEED": hash_seed},
                text=True,
                timeout=20,
            )
        )
        for hash_seed in ("1", "2")
    ]
    first, second = snapshots
    assert first.keys() == second.keys()
    for scenario_id in first:
        assert first[scenario_id] == second[scenario_id], scenario_id


if __name__ == "__main__":
    print(json.dumps(_audit_twice()))
