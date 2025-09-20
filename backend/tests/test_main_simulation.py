import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.anyio("asyncio")
async def test_simulate_endpoint_returns_confidence_and_timecourse() -> None:
    payload = {
        "receptors": {
            "5HT1A": {"occ": 0.6, "mech": "agonist"},
            "5HT2A": {"occ": 0.3, "mech": "antagonist"},
            "UNKNOWN": {"occ": 0.4, "mech": "agonist"},
        },
        "adhd": True,
        "gut_bias": False,
        "pvt_weight": 0.4,
        "dosing": "chronic",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/simulate", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert "confidence" in data
    assert "DriveInvigoration" in data["scores"]
    assert 0.0 <= data["confidence"]["DriveInvigoration"] <= 1.0
    assert len(data["details"]["timepoints"]) == len(
        data["details"]["trajectories"]["plasma_concentration"]
    )
    assert data["details"]["timepoints"][-1] >= 168.0
    assert "UNKNOWN" in data["details"]["ignored_receptors"]
