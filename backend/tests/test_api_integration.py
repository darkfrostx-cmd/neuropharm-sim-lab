import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as instance:
        yield instance


@pytest.fixture()
def anyio_backend():
    return "asyncio"


async def test_evidence_search_returns_results(serotonin_graph, client):
    response = await client.post("/evidence/search", json={"object": "HGNC:HTR1A"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["edge"]["object"] == "HGNC:HTR1A"
    assert data["items"][0]["provenance"][0]["source"] == "ChEMBL"
    quality = data["items"][0]["quality"]
    assert "score" in quality and quality["score"] is not None
    assert quality["species_distribution"]
    assert data["items"][0]["provenance"][0]["quality"]["total_score"] >= 0.0


async def test_evidence_search_rejects_unknown_predicate(client):
    response = await client.post("/evidence/search", json={"predicate": "biolink:not_a_predicate"})
    assert response.status_code == 422


async def test_graph_expand_returns_fragment(serotonin_graph, client):
    response = await client.post("/graph/expand", json={"node_id": "HGNC:HTR1A", "depth": 1, "limit": 10})
    assert response.status_code == 200
    data = response.json()
    assert any(node["id"] == "HGNC:HTR1A" for node in data["nodes"])
    assert data["centre"] == "HGNC:HTR1A"


async def test_graph_expand_missing_node_returns_404(client):
    response = await client.post("/graph/expand", json={"node_id": "HGNC:UNKNOWN"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "node_not_found"


async def test_predict_effects_returns_bundle(serotonin_graph, client):
    response = await client.post("/predict/effects", json={"receptors": [{"name": "5HT1A"}]})
    assert response.status_code == 200
    data = response.json()
    effect = data["items"][0]
    assert effect["receptor"] == "5-HT1A"
    assert effect["evidence"] >= 0.0
    assert effect["uncertainty"] <= 1.0


async def test_predict_effects_unknown_receptor(client):
    response = await client.post("/predict/effects", json={"receptors": [{"name": "NOPE"}]})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "receptor_not_supported"


async def test_simulate_endpoint_returns_confidence_and_timecourse(serotonin_graph, client):
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
    response = await client.post("/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "DriveInvigoration" in data["scores"]
    assert 0.0 <= data["confidence"]["DriveInvigoration"] <= 1.0
    assert data["behavioral_tags"]["DriveInvigoration"]["rdoc"]["id"] == "RDoC:POS_APPR"
    assert len(data["details"]["timepoints"]) == len(data["details"]["trajectories"]["plasma_concentration"])
    assert data["details"]["receptor_context"]["5-HT1A"]["kg_weight"] >= data["details"]["receptor_context"]["5-HT2A"]["kg_weight"]


async def test_simulate_requires_receptors(client):
    response = await client.post("/simulate", json={"receptors": {}, "dosing": "acute"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "no_receptors"


async def test_explain_returns_edges(serotonin_graph, client):
    response = await client.post("/explain", json={"receptor": "5HT1A", "direction": "both", "limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["canonical_receptor"] == "5-HT1A"
    assert data["edges"]
    assert {edge["direction"] for edge in data["edges"]} <= {"upstream", "downstream"}


async def test_explain_unknown_receptor(client):
    response = await client.post("/explain", json={"receptor": "XYZ"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "receptor_not_supported"


async def test_gaps_endpoint_lists_missing_edges(serotonin_graph, client):
    response = await client.post(
        "/gaps",
        json={"focus_nodes": ["HGNC:HTR1A", "HGNC:HTR2A"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"]
    gap = data["items"][0]
    assert "reason" in gap
    assert "embedding_score" in gap
    assert "context" in gap and "context_weight" in gap["context"]
    assert "literature" in gap


async def test_gaps_missing_node_returns_error(client):
    response = await client.post(
        "/gaps",
        json={"focus_nodes": ["HGNC:HTR1A", "HGNC:DOESNOTEXIST"]},
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "nodes_not_found"


async def test_atlas_overlay_endpoint_returns_coordinates(monkeypatch, client):
    stub_overlay = AtlasOverlay(
        node_id="UBERON:0000955",
        provider="Allen Brain Atlas",
        coordinates=[AtlasCoordinate(reference_space=10, x_mm=7.5, y_mm=6.6, z_mm=4.7, source="allen")],
        volumes=[
            AtlasVolume(
                name="Allen test volume",
                url="https://example.org/atlas.nrrd",
                format="nrrd",
                metadata={"type": "segmentation"},
            )
        ],
    )

    class StubAtlasService:
        def lookup(self, node_id: str) -> AtlasOverlay:
            if node_id != stub_overlay.node_id:
                raise KeyError(node_id)
            return stub_overlay

    from backend.api import routes as api_routes

    monkeypatch.setattr(api_routes.services, "atlas_service", StubAtlasService())

    response = await client.get(f"/atlas/overlays/{stub_overlay.node_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == stub_overlay.node_id
    assert data["provider"] == "Allen Brain Atlas"
    assert data["coordinates"][0]["x_mm"] == 7.5
    assert data["volumes"][0]["format"] == "nrrd"
from backend.atlas import AtlasCoordinate, AtlasOverlay, AtlasVolume
