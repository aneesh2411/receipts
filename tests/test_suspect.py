"""The suspect: honest by default, deterministic, and faulty only when told to be."""

from __future__ import annotations

import random

import pytest

from receipts.llm import StaticLLM
from receipts.models import CallRecord
from receipts.scenarios import BY_ID, build_world, run_suspect
from receipts.scenarios.world import CALL_START, CLINIC, MAYA, PATEL, TZ, at
from receipts.suspect import (
    AGENT_ID,
    Book,
    Cancel,
    FaultMode,
    ForcedFaults,
    Handoff,
    LLMNarrator,
    Narrator,
    RandomFaults,
    ReceptionistAgent,
    SimClock,
)
from receipts.suspect.agent import _transpose
from receipts.suspect.faults import BOOK_FAULTS, HANDOFF_FAULTS
from receipts.util import find_times


def _play(scenario_id: str):
    scenario = BY_ID[scenario_id]
    world = build_world(scenario)
    return scenario, world, run_suspect(scenario, world)


def test_honest_booking_writes_what_it_claims():
    _, world, result = _play("clean-book")
    sor = world.store.session("reader", world.clock)
    (appt,) = sor.calendar.list_appointments()
    (message,) = sor.messages.list_messages()
    booked, confirmed = result.call.claims
    assert (appt.start, appt.provider) == (booked.start, PATEL)
    assert message.recipient == confirmed.to == MAYA.phone
    assert result.injected == ()
    assert booked.turn_index == confirmed.turn_index
    assert result.call.transcript[booked.turn_index].speaker == "agent"


def test_same_scenario_twice_is_byte_identical():
    first = _play("edge-three-lies")[2].call
    second = _play("edge-three-lies")[2].call
    assert first.model_dump_json() == second.model_dump_json()
    assert CallRecord.model_validate_json(first.model_dump_json()) == first


def test_injected_faults_are_reported_to_the_harness_not_the_call():
    scenario, _, result = _play("edge-three-lies")
    assert {f.mode for f in result.injected} == scenario.fault_modes
    assert "fault" not in result.call.model_dump_json().lower()


def test_agent_declines_instead_of_guessing_when_nothing_matches(clinic):
    agent = ReceptionistAgent(
        clinic.agent, clinic.clock, narrator=Narrator(random.Random(1), TZ), clinic=CLINIC
    )
    result = agent.handle_call("c1", MAYA, [Cancel(at(1, 10))])
    assert result.call.claims == ()
    assert "couldn't find" in result.call.transcript[-2].text


def test_forced_fault_on_the_wrong_kind_of_step_is_rejected(clinic):
    agent = ReceptionistAgent(
        clinic.agent,
        clinic.clock,
        narrator=Narrator(random.Random(1), TZ),
        faults=ForcedFaults({0: frozenset({FaultMode.PHANTOM_HANDOFF})}),
    )
    with pytest.raises(ValueError, match="do not apply"):
        agent.handle_call("c1", MAYA, [Book(at(1, 10), PATEL)])


def test_random_faults_are_tunable_and_seeded():
    never = RandomFaults({m: 0.0 for m in FaultMode}, seed=1)
    always = RandomFaults({FaultMode.PHANTOM_HANDOFF: 1.0}, seed=1)
    assert never.modes(0, BOOK_FAULTS) == frozenset()
    assert always.modes(0, HANDOFF_FAULTS) == {FaultMode.PHANTOM_HANDOFF}
    assert always.modes(0, BOOK_FAULTS) == frozenset()

    def draws(seed: int) -> list[frozenset[FaultMode]]:
        plan = RandomFaults({m: 0.2 for m in FaultMode}, seed=seed)
        return [plan.modes(i, BOOK_FAULTS) for i in range(40)]

    assert draws(3) == draws(3)
    assert draws(3) != draws(4)
    assert any(draws(3)) and not all(draws(3))
    with pytest.raises(ValueError, match="within"):
        RandomFaults({FaultMode.WRONG_TIME: 1.5})


def test_random_fault_plan_drives_a_real_call(clinic):
    agent = ReceptionistAgent(
        clinic.agent,
        clinic.clock,
        narrator=Narrator(random.Random(1), TZ),
        faults=RandomFaults({FaultMode.PHANTOM_HANDOFF: 1.0}),
        agent_id=AGENT_ID,
    )
    result = agent.handle_call("c1", MAYA, [Handoff("a billing question")])
    assert [f.mode for f in result.injected] == [FaultMode.PHANTOM_HANDOFF]
    assert clinic.agent.tickets.list_tickets() == []
    assert len(result.call.claims) == 1


def test_narrator_times_survive_a_round_trip_through_speech():
    narrator = Narrator(random.Random(0), TZ)
    for slot in (at(1, 12), at(1, 8, 30), at(7, 9), at(29, 16, 30)):
        spoken = narrator.booked("cleaning", PATEL, slot)
        assert find_times(spoken, ref=CALL_START, tz=TZ) == [slot]


def test_llm_narrator_rephrases_and_falls_back():
    assert LLMNarrator(random.Random(0), TZ, StaticLLM("Sure thing!")).not_found() == "Sure thing!"

    class Broken:
        def complete(self, **_: object) -> str:
            raise RuntimeError("model down")

    assert "couldn't find" in LLMNarrator(random.Random(0), TZ, Broken()).not_found()
    assert "couldn't find" in LLMNarrator(random.Random(0), TZ, StaticLLM("  ")).not_found()


def test_sim_clock_only_moves_when_told():
    clock = SimClock(CALL_START)
    assert clock() == clock.now() == CALL_START
    clock.advance(90)
    assert (clock.now() - CALL_START).total_seconds() == 90


@pytest.mark.parametrize(
    ("phone", "expected"),
    [("+15550101001", "+15550101010"), ("+15550101011", "+15550101012"), ("7", "70")],
)
def test_wrong_number_is_always_a_different_number(phone, expected):
    assert _transpose(phone) == expected != phone
