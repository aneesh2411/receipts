"""Extraction health: a degraded model fallback must not look like a healthy run."""

from subpoena.auditor import LLMClaimExtractor, RuleBasedExtractor, render_markdown
from subpoena.llm import StaticLLM
from subpoena.scenarios.world import CLINIC


class Down:
    def complete(self, **_: object) -> str:
        raise RuntimeError("model unavailable")


_LINE = "I've booked you with Dr. Kim on Tuesday, March 3 at 2:30 PM."


def test_rules_only_run_is_healthy(clinic):
    report = clinic.audit(clinic.call([]))
    assert report.extraction.extractor == "rules"
    assert report.extraction.degraded is False
    assert report.extraction.detail is None


def test_transcript_reader_off_reports_none(clinic):
    report = clinic.audit(clinic.call([]), use_transcript=False)
    assert report.extraction.extractor == "none"
    assert report.extraction.degraded is False


def test_failed_model_marks_the_run_degraded(clinic):
    call = clinic.call(agent_lines=[_LINE])
    expected = RuleBasedExtractor().extract(call, CLINIC)
    report = clinic.audit(call, extractor=LLMClaimExtractor(Down()))
    assert report.extraction.degraded is True
    assert report.extraction.extractor == "rules"
    assert "llm:unknown" in (report.extraction.detail or "")
    assert "RuntimeError" in (report.extraction.detail or "")
    # the claims still come from the rules, so they match the rules-only run
    assert len(report.verdicts) == len(expected) or expected == []
    baseline = clinic.audit(call)
    assert [v.claim.type for v in report.verdicts] == [v.claim.type for v in baseline.verdicts]


def test_working_model_reports_its_name(clinic):
    report = clinic.audit(
        clinic.call(agent_lines=[_LINE]),
        extractor=LLMClaimExtractor(StaticLLM("[]"), name="llm:test-model"),
    )
    assert report.extraction.extractor == "llm:test-model"
    assert report.extraction.degraded is False


def test_report_renders_extraction_health(clinic):
    healthy = render_markdown(clinic.audit(clinic.call([])))
    assert "- Extraction: `rules`" in healthy
    assert "degraded" not in healthy
    degraded = render_markdown(
        clinic.audit(clinic.call(agent_lines=[_LINE]), extractor=LLMClaimExtractor(Down()))
    )
    assert "degraded" in degraded
