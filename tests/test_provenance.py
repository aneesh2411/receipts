"""Per-call provenance: platform-supplied config, sealed with the report."""

from __future__ import annotations

from receipts.auditor import Sealer
from receipts.auditor.render import render_markdown
from receipts.models import Provenance
from receipts.scenarios import BY_ID, run_scenario


def test_call_record_without_provenance_still_validates(clinic):
    call = clinic.call()
    assert call.provenance is None


def test_suspect_stamps_its_own_provenance():
    run = run_scenario(BY_ID["clean-book"])
    prov = run.result.call.provenance
    assert prov is not None
    assert prov.agent_version.startswith("receptionist-sim/")
    assert prov.prompt_version in ("narrator:standard", "narrator:hard")
    assert prov.model is None  # the suspect is scripted; it must not pose as a model


def test_hard_phrasing_is_a_distinct_prompt_version():
    soft = run_scenario(BY_ID["clean-book"]).result.call.provenance
    hard_ids = [sid for sid, s in BY_ID.items() if s.hard_phrasing]
    hard = run_scenario(BY_ID[hard_ids[0]]).result.call.provenance
    assert soft.prompt_version == "narrator:standard"
    assert hard.prompt_version == "narrator:hard"


def test_report_markdown_renders_provenance_as_unverified():
    report = run_scenario(BY_ID["clean-book"]).report
    md = render_markdown(report)
    assert "Provenance (platform-supplied, unverified)" in md
    assert report.call.provenance.agent_version in md


def test_no_provenance_no_line(clinic):
    report = clinic.audit(clinic.call())
    assert report.call.provenance is None
    assert "Provenance" not in render_markdown(report)


def test_provenance_is_covered_by_the_seal(clinic):
    sealer = Sealer(b"test-key")
    sealed = sealer.seal(clinic.audit(clinic.call()))
    tampered = sealed.model_copy(
        update={
            "call": sealed.call.model_copy(
                update={"provenance": Provenance(agent_version="receptionist-sim/9.9.9")}
            )
        }
    )
    assert sealer.verify(sealed).ok
    assert not sealer.verify(tampered).ok
