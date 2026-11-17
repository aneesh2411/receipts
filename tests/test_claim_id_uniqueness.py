"""Regression: two claims sharing one claim_id must not both verify one write.

Found by independent review (docs/FAILURE_ANALYSIS.md section 4, item 1): call
records did not enforce unique ids, and the reconciler keyed matches by
claim_id, so a duplicated id let two claims consume a single write. The record
is now rejected at the door.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from receipts.api import Settings, create_app
from receipts.models import AppointmentBooked
from receipts.scenarios import BY_ID, build_world, run_suspect


def _staged_call(scenario_id: str = "fault-phantom-booking"):
    scenario = BY_ID[scenario_id]
    world = build_world(scenario)
    try:
        return run_suspect(scenario, world).call
    finally:
        world.store.close()


def test_duplicate_claim_ids_are_rejected(clinic) -> None:
    claim = AppointmentBooked(
        claim_id="dup",
        turn_index=0,
        patient=clinic.call().caller,
        start=clinic.call().started_at,
    )
    with pytest.raises(ValidationError, match="duplicate claim_id"):
        clinic.call(claims=(claim, claim))


def test_api_rejects_duplicate_claim_ids() -> None:
    client = TestClient(create_app(Settings(signing_key=b"k")))
    payload = _staged_call().model_dump(mode="json")
    payload["claims"] = [payload["claims"][0], payload["claims"][0]]
    response = client.post("/calls", json=payload)
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert "duplicate claim_id" in response.json()["error"]
