"""Integration tests for the FastAPI routes using httpx."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.api.routes import get_graph_service, get_simulation_engine
from backend.engine.simulator import SimulationEngine
from backend.graph.models import BiolinkEntity, BiolinkPredicate, Edge, Evidence, Node
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService


@pytest.fixture()
def anyio_backend() -> str:  # pragma: no cover - restrict to asyncio for anyio plugin
    return "asyncio"


@pytest.fixture()
def graph_service_fixture() -> GraphService:
    store = InMemoryGraphStore()
    service = GraphService(store=store)

    nodes = [
        Node(id="HGNC:5", name="SLC6A4", category=BiolinkEntity.GENE),
        Node(id="CHEMBL:25", name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE),
        Node(id="HGNC:6", name="MAOA", category=BiolinkEntity.GENE),
    ]

    edges = [
        Edge(
            subject="HGNC:5",
            predicate=BiolinkPredicate.AFFECTS,
            object="CHEMBL:25",
            relation="biolink:affects",
            knowledge_level="supported by literature",
            evidence=[
                Evidence(source="INDRA", reference="PMID:123", confidence=0.8, annotations={"statement": "Example"}),
                Evidence(source="ChEMBL", reference="CHEMBL:XYZ", confidence=0.6, annotations={"assay": "IC50"}),
            ],
        ),
        Edge(
            subject="HGNC:6",
            predicate=BiolinkPredicate.RELATED_TO,
            object="CHEMBL:25",
            relation="biolink:related_to",
            knowledge_level="observed",
            evidence=[Evidence(source="OpenAlex", reference="10.1000/example", confidence=0.7)],
        ),
    ]

    service.persist(nodes, edges)
    return service


@pytest.fixture()
async def test_client(graph_service_fixture: GraphService):
    app.dependency_overrides[get_graph_service] = lambda: graph_service_fixture
    app.dependency_overrides[get_simulation_engine] = SimulationEngine
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.anyio("asyncio")
async def test_evidence_search_returns_filtered_results(test_client: AsyncClient) -> None:
    payload = {
        "filters": {"subject": "HGNC:5", "source": "INDRA"},
        "pagination": {"page": 1, "size": 10},
    }
    response = await test_client.post("/evidence/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["results"][0]["edge"]["subject"] == "HGNC:5"
    assert data["results"][0]["total_evidence"] == 1


@pytest.mark.anyio("asyncio")
async def test_evidence_search_with_unknown_source(test_client: AsyncClient) -> None:
    payload = {
        "filters": {"subject": "HGNC:5", "source": "NON_EXISTENT"},
        "pagination": {"page": 1, "size": 10},
    }
    response = await test_client.post("/evidence/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["results"] == []


@pytest.mark.anyio("asyncio")
async def test_graph_expand_supports_category_filters(test_client: AsyncClient) -> None:
    payload = {
        "node_id": "CHEMBL:25",
        "depth": 1,
        "limit": 10,
        "category_filter": [BiolinkEntity.CHEMICAL_SUBSTANCE.value],
    }
    response = await test_client.post("/graph/expand", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "CHEMBL:25"


@pytest.mark.anyio("asyncio")
async def test_predict_effects_returns_top_scores(test_client: AsyncClient) -> None:
    payload = {
        "compound_id": "CHEMBL:25",
        "simulation": {
            "receptors": {"5-HT2C": {"occ": 0.5, "mech": "antagonist"}},
            "acute_1a": False,
            "adhd": False,
            "gut_bias": False,
            "pvt_weight": 0.2,
        },
        "top_n": 2,
    }
    response = await test_client.post("/predict/effects", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["predicted_effects"]) == 2
    assert {effect["metric"] for effect in data["predicted_effects"]}


@pytest.mark.anyio("asyncio")
async def test_predict_effects_invalid_mechanism_returns_error(test_client: AsyncClient) -> None:
    payload = {
        "compound_id": "CHEMBL:25",
        "simulation": {
            "receptors": {"5-HT2C": {"occ": 0.5, "mech": "unknown"}},
        },
        "top_n": 1,
    }
    response = await test_client.post("/predict/effects", json=payload)
    assert response.status_code == 400


@pytest.mark.anyio("asyncio")
async def test_simulate_returns_scores_and_citations(test_client: AsyncClient) -> None:
    payload = {
        "receptors": {"5-HT2C": {"occ": 0.5, "mech": "antagonist"}},
        "adhd": True,
    }
    response = await test_client.post("/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "DriveInvigoration" in data["scores"]
    assert "provenance" in data


@pytest.mark.anyio("asyncio")
async def test_explain_limits_evidence(test_client: AsyncClient) -> None:
    payload = {
        "subject": "HGNC:5",
        "object": "CHEMBL:25",
        "predicate": BiolinkPredicate.AFFECTS.value,
        "max_evidence": 1,
    }
    response = await test_client.post("/explain", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["explanations"]) == 1
    assert len(data["explanations"][0]["evidence"]) == 1


@pytest.mark.anyio("asyncio")
async def test_gaps_endpoint_identifies_missing_connections(test_client: AsyncClient) -> None:
    payload = {"focus_nodes": ["HGNC:5", "HGNC:6", "CHEMBL:25"]}
    response = await test_client.post("/gaps", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert all("reason" in gap for gap in data["gaps"])


@pytest.mark.anyio("asyncio")
async def test_invalid_pagination_rejected(test_client: AsyncClient) -> None:
    payload = {
        "filters": {"subject": "HGNC:5"},
        "pagination": {"page": 1, "size": 500},
    }
    response = await test_client.post("/evidence/search", json=payload)
    assert response.status_code == 422
