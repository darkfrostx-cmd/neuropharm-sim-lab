"""Integration tests covering the assistant aggregation endpoints."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("GRAPH_AUTO_BOOTSTRAP", "0")

from backend.main import app


pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture()
async def client():
    """Provide an async HTTP client bound to the FastAPI app."""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as instance:
        yield instance


@pytest.fixture()
def anyio_backend():
    return "asyncio"


async def test_assistant_capabilities_exposes_actions(client):
    response = await client.get("/assistant/capabilities")
    assert response.status_code == 200
    data = response.json()
    actions = {item["action"] for item in data["actions"]}
    assert "predict_effects" in actions
    assert "simulate" in actions
    effect_entry = next(item for item in data["actions"] if item["action"] == "predict_effects")
    assert effect_entry["endpoint"] == "/predict/effects"
    assert effect_entry["payload_schema"]["type"] == "object"


async def test_assistant_execute_predict_effects(serotonin_graph, client):
    payload = {"action": "predict_effects", "payload": {"receptors": [{"name": "5HT1A"}]}}
    response = await client.post("/assistant/execute", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "predict_effects"
    assert data["source_endpoint"] == "/predict/effects"
    effect = data["result"]["items"][0]
    assert effect["receptor"] == "5-HT1A"
    assert data["normalized_payload"]["receptors"][0]["name"] == "5HT1A"


async def test_assistant_execute_reports_validation_errors(client):
    response = await client.post("/assistant/execute", json={"action": "atlas_overlay", "payload": {}})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_payload"
    first_error = detail["context"]["errors"][0]
    assert first_error["loc"][-1] == "node_id"
