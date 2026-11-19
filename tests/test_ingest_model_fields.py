"""Ingest-supplied fields are carried, never trusted.

``CallRecord.raw_transcript`` is a text-only platform transcription: it has no
timing and no speaker roles, so nothing on the verdict path may read it. The
provenance fields name what the platform claimed. Neither may change a verdict.
"""

from __future__ import annotations

from subpoena.scenarios.world import PATEL, Scenario, at, audit_call, build_world, run_suspect
from subpoena.suspect import Book

SLOT = at(1, 14, 30)

_INGEST_EXTRAS = {
    "raw_transcript": "caller: book me tuesday agent: you are booked for tuesday at two thirty",
    "provenance": {
        "agent_version": "ingest-test",
        "platform": "twilio",
        "from_address": "+12025550101",
        "to_address": "+12025550102",
    },
}


def _report(with_extras: bool):
    scenario = Scenario(
        "test-ingest-fields",
        "Honest booking",
        "x",
        (Book(start=SLOT, provider=PATEL),),
        (),
    )
    world = build_world(scenario)
    result = run_suspect(scenario, world)
    call = result.call
    if with_extras:
        provenance = call.provenance.model_copy(
            update=_INGEST_EXTRAS["provenance"]
        ) if call.provenance else None
        from subpoena.models import Provenance

        call = call.model_copy(
            update={
                "raw_transcript": _INGEST_EXTRAS["raw_transcript"],
                "provenance": provenance or Provenance(**_INGEST_EXTRAS["provenance"]),
            }
        )
    return audit_call(scenario, world, type(result)(call=call, injected=result.injected))


def test_ingest_fields_do_not_change_verdicts():
    plain = _report(False)
    enriched = _report(True)
    assert [v.status for v in plain.verdicts] == [v.status for v in enriched.verdicts]
    assert [f.code for f in plain.findings] == [f.code for f in enriched.findings]


def test_ingest_fields_are_carried_into_the_report():
    report = _report(True)
    assert report.call.raw_transcript == _INGEST_EXTRAS["raw_transcript"]
    assert report.call.provenance.platform == "twilio"
    assert report.call.provenance.from_address == "+12025550101"
