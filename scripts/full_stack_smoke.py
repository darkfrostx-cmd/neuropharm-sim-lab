"""End-to-end smoke test that exercises the public API routes."""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app


def _simulate_payload() -> dict[str, object]:
    return {
        "receptors": {
            "5HT1A": {"occ": 0.6, "mech": "agonist"},
            "5HT2A": {"occ": 0.2, "mech": "antagonist"},
        },
        "dosing": "chronic",
        "adhd": False,
        "gut_bias": True,
        "pvt_weight": 0.3,
    }


def main() -> None:
    with TestClient(app) as client:
        health = client.get("/assistant/capabilities")
        health.raise_for_status()
        capabilities = health.json()
        assert "actions" in capabilities and capabilities["actions"], "Capabilities payload is empty"

        simulation = client.post("/simulate", json=_simulate_payload())
        simulation.raise_for_status()
        data = simulation.json()
        assert data["scores"], "Simulation returned no scores"
        assert data["engine"]["backends"], "Engine metadata missing backends"
        assert set(data["engine"]["backends"]) == {"molecular", "pkpd", "circuit"}
        for module, backend_name in data["engine"]["backends"].items():
            assert backend_name, f"Backend for {module} not reported"
        assert data["details"]["trajectories"], "Trajectories payload missing"

        evidence = client.post(
            "/evidence/search",
            json={"subject": "HGNC:HTR1A", "object": "HP:0000716", "page": 1, "size": 5},
        )
        evidence.raise_for_status()
        evidence_payload = evidence.json()
        assert evidence_payload["items"] is not None
 

if __name__ == "__main__":
    main()
