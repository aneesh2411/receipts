"""The golden dataset: labels hold, known gaps stay honest, runs are reproducible."""

from __future__ import annotations

import pytest

from subpoena.evals import score_run
from subpoena.models import Outcome
from subpoena.scenarios import GOLDEN, run_scenario

SOLVED = [s for s in GOLDEN if not s.known_gap]
GAPS = [s for s in GOLDEN if s.known_gap]


def _score(scenario):
    report = run_scenario(scenario).report
    return report, score_run(
        scenario.id, scenario.expected_claims, scenario.expected_findings, report
    )


@pytest.mark.parametrize("scenario", SOLVED, ids=lambda s: s.id)
def test_auditor_matches_the_hand_written_label(scenario):
    report, score = _score(scenario)
    assert score.problems == ()
    assert (report.outcome is not Outcome.CLEAN) == scenario.expected_dirty


@pytest.mark.parametrize("scenario", GAPS, ids=lambda s: s.id)
def test_known_gaps_are_still_gaps(scenario):
    """If one of these starts passing, the gap is closed: drop its known_gap label."""
    _, score = _score(scenario)
    assert score.problems, f"{scenario.id} now passes; remove known_gap and celebrate"


def test_dataset_shape():
    assert len(GOLDEN) >= 40
    assert len({s.id for s in GOLDEN}) == len(GOLDEN)
    clean = [s for s in GOLDEN if not s.expected_dirty]
    assert len(clean) >= 10, "an auditor that cries wolf must be penalised"
    assert len(GAPS) <= 3, "known gaps are a short honest list, not a dumping ground"


@pytest.mark.parametrize("scenario", GOLDEN[:8] + GOLDEN[-6:], ids=lambda s: s.id)
def test_reports_are_reproducible_bit_for_bit(scenario):
    first = run_scenario(scenario).report
    second = run_scenario(scenario).report
    assert first.model_dump_json() == second.model_dump_json()
    assert first.seal is not None and first.seal == second.seal


def test_every_verdict_carries_three_checks_and_a_trail():
    for scenario in SOLVED:
        report = run_scenario(scenario).report
        stages = {e.stage for e in report.trail}
        assert {"claims", "evidence", "verdict"} <= stages
        assert [e.seq for e in report.trail] == list(range(1, len(report.trail) + 1))
        for verdict in report.verdicts:
            if verdict.status.value != "UNVERIFIABLE":
                assert [c.name.value for c in verdict.checks] == [
                    "existence",
                    "exactness",
                    "side_effects",
                ]
