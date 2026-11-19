"""Multi-intent fuzzing: composed truth must match what the auditor reports."""

from subpoena.evals.fuzz import generate
from subpoena.evals.run import evaluate, run_all
from subpoena.suspect.faults import FaultMode as F


def test_generation_is_deterministic():
    a, b = generate(40, 7), generate(40, 7)
    assert [s.id for s in a] == [s.id for s in b]
    assert [s.expected_claims for s in a] == [s.expected_claims for s in b]


def test_population_mixes_single_and_multi_intent():
    scenarios = generate(500, 7)
    multi = [s for s in scenarios if len(s.steps) > 1]
    single = [s for s in scenarios if len(s.steps) == 1]
    assert len(single) > len(multi) > 0
    assert all(len(s.steps) <= 3 for s in multi)


def test_multi_intent_never_rewrites_identity_mid_call():
    for s in generate(500, 7):
        if len(s.steps) > 1:
            modes = {m for modes in s.faults.values() for m in modes}
            assert F.SILENT_CRM_EDIT not in modes


def test_multi_intent_truth_matches_the_auditor():
    multi = [s for s in generate(80, 3) if len(s.steps) > 1]
    assert multi
    report = evaluate(multi, label="multi")
    assert report.strict_accuracy == 1.0, [
        (f.scenario, f.category, f.detail) for f in report.failures
    ]


def test_multi_intent_calls_include_fault_mixes():
    multi = [s for s in generate(200, 7) if len(s.steps) > 1]
    assert any(s.faults for s in multi), "no faults in any multi-intent call"
    assert any(len(s.faults) > 1 for s in multi), "no multi-fault call"
    assert any(not s.faults for s in multi), "no fully honest multi-intent call"


def test_fuzz_scenarios_carry_v2_labels_in_step_order():
    scenarios = generate(30, 7)
    for s in scenarios:
        assert len(s.expected_claims_v2) == len(s.expected_claims)
        for (t1, s1), (t2, s2, identity) in zip(
            s.expected_claims, s.expected_claims_v2, strict=True
        ):
            assert (t1, s1) == (t2, s2)
            assert "|" in identity


def test_fuzz_v2_scores_like_positional():
    result = run_all(fuzz_n=40, fuzz_seed=7)
    assert result.fuzz_v2 is not None
    assert result.fuzz_v2.calls == 40
    assert round(result.fuzz_v2.strict_accuracy, 4) == round(result.fuzz.strict_accuracy, 4)
