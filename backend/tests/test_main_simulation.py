from fastapi.testclient import TestClient

from backend.main import app


def test_simulate_endpoint_returns_confidence_and_timecourse(serotonin_graph):
    client = TestClient(app)
    payload = {
        "receptors": {
            "5HT1A": {"occ": 0.6, "mech": "agonist"},
            "5HT2A": {"occ": 0.3, "mech": "antagonist"},
        },
        "adhd": True,
        "gut_bias": False,
        "pvt_weight": 0.4,
        "dosing": "chronic",
    }

    response = client.post("/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "confidence" in data
    assert "DriveInvigoration" in data["scores"]
    assert 0.0 <= data["confidence"]["DriveInvigoration"] <= 1.0
    assert len(data["details"]["timepoints"]) == len(data["details"]["trajectories"]["plasma_concentration"])
    assert data["details"]["timepoints"][-1] >= 168.0

    ctx_1a = data["details"]["receptor_context"]["5-HT1A"]
    ctx_2a = data["details"]["receptor_context"]["5-HT2A"]
    assert ctx_1a["kg_weight"] > ctx_2a["kg_weight"]
    assert ctx_1a["affinity"] is not None
    assert "ChEMBL" in ctx_1a["sources"]
