import pytest
from httpx import ASGITransport, AsyncClient

from backend.graph.models import BiolinkEntity, BiolinkPredicate, Edge, Evidence, Node
from backend.graph.persistence import InMemoryGraphStore
from backend.main import app


@pytest.fixture(autouse=True)
def reset_graph_store() -> None:
    service = app.state.graph_service
    service.store = InMemoryGraphStore()


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def seed_basic_graph() -> None:
    service = app.state.graph_service
    node_a = Node(id="CHEMBL:25", name="Example Compound", category=BiolinkEntity.CHEMICAL_SUBSTANCE)
    node_b = Node(id="HP:0001250", name="Seizures", category=BiolinkEntity.PHENOTYPIC_FEATURE)
    service.persist([node_a, node_b], [])

    edge = Edge(
        subject=node_a.id,
        predicate=BiolinkPredicate.AFFECTS,
        object=node_b.id,
        knowledge_level="supporting",
        confidence=0.82,
        publications=["PMID:1"],
        evidence=[Evidence(source="ChEMBL", reference="PMID:1", confidence=0.82, uncertainty="medium")],
    )
    service.persist([], [edge])


@pytest.mark.anyio("asyncio")
async def test_evidence_search_returns_paginated_results(client: AsyncClient) -> None:
    seed_basic_graph()

    response = await client.post(
        "/evidence/search",
        json={
            "subject": "CHEMBL:25",
            "predicate": BiolinkPredicate.AFFECTS.value,
            "page": 1,
            "page_size": 10,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["results"][0]["subject"] == "CHEMBL:25"
    assert payload["results"][0]["evidence"][0]["source"] == "ChEMBL"


@pytest.mark.anyio("asyncio")
async def test_evidence_search_empty_results(client: AsyncClient) -> None:
    response = await client.post(
        "/evidence/search",
        json={"subject": "CHEMBL:999", "page": 1, "page_size": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["results"] == []


@pytest.mark.anyio("asyncio")
async def test_evidence_search_validation_error(client: AsyncClient) -> None:
    response = await client.post(
        "/evidence/search",
        json={"page": 0, "page_size": 0},
    )
    assert response.status_code == 422


@pytest.mark.anyio("asyncio")
async def test_graph_expand_returns_nodes_and_edges(client: AsyncClient) -> None:
    seed_basic_graph()

    response = await client.post(
        "/graph/expand",
        json={"node_id": "CHEMBL:25", "depth": 1, "limit": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert any(node["id"] == "CHEMBL:25" for node in payload["nodes"])
    assert payload["edges"]


@pytest.mark.anyio("asyncio")
async def test_predict_effects_returns_scores_and_contributions(client: AsyncClient) -> None:
    response = await client.post(
        "/predict/effects",
        json={
            "receptors": {"5HT1A": {"occ": 0.5, "mech": "agonist"}},
            "dosing": "acute",
            "gut_bias": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Motivation" in payload["scores"]
    assert payload["contributions"]
    assert payload["uncertainty"]["Motivation"] >= 0.0


@pytest.mark.anyio("asyncio")
async def test_predict_effects_reports_ignored_targets(client: AsyncClient) -> None:
    response = await client.post(
        "/predict/effects",
        json={"receptors": {"NotAReceptor": {"occ": 0.3, "mech": "agonist"}}},
    )
    assert response.status_code == 200
    assert response.json()["ignored_targets"] == ["NotAReceptor"]


@pytest.mark.anyio("asyncio")
async def test_predict_effects_validation_error_for_mechanism(client: AsyncClient) -> None:
    response = await client.post(
        "/predict/effects",
        json={"receptors": {"5HT1A": {"occ": 0.5, "mech": "invalid"}}},
    )
    assert response.status_code == 422


@pytest.mark.anyio("asyncio")
async def test_explain_endpoint_returns_drivers(client: AsyncClient) -> None:
    response = await client.post(
        "/explain",
        json={
            "receptors": {
                "5HT1A": {"occ": 0.6, "mech": "agonist"},
                "5HT2A": {"occ": 0.2, "mech": "antagonist"},
            },
            "metric": "Motivation",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["metric"] == "Motivation"
    assert payload["drivers"]
    assert "Estimated uncertainty" in payload["summary"]


@pytest.mark.anyio("asyncio")
async def test_explain_endpoint_rejects_unknown_metric(client: AsyncClient) -> None:
    response = await client.post(
        "/explain",
        json={"receptors": {"5HT1A": {"occ": 0.5, "mech": "agonist"}}, "metric": "invalid"},
    )
    assert response.status_code == 422


@pytest.mark.anyio("asyncio")
async def test_gaps_endpoint_identifies_missing_edges(client: AsyncClient) -> None:
    service = app.state.graph_service
    node_a = Node(id="HGNC:5", name="GeneA", category=BiolinkEntity.GENE)
    node_b = Node(id="HGNC:6", name="GeneB", category=BiolinkEntity.GENE)
    service.persist([node_a, node_b], [])

    response = await client.post("/gaps", json={"focus": [node_a.id, node_b.id]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["gaps"]
    assert payload["gaps"][0]["subject"] == node_a.id


@pytest.mark.anyio("asyncio")
async def test_gaps_endpoint_handles_empty_result(client: AsyncClient) -> None:
    service = app.state.graph_service
    node_a = Node(id="HGNC:7", name="GeneC", category=BiolinkEntity.GENE)
    node_b = Node(id="HGNC:8", name="GeneD", category=BiolinkEntity.GENE)
    service.persist([node_a, node_b], [])
    connecting_edge = Edge(
        subject=node_a.id,
        predicate=BiolinkPredicate.RELATED_TO,
        object=node_b.id,
        evidence=[Evidence(source="OpenAlex", reference="10.1000/example")],
    )
    service.persist([], [connecting_edge])

    response = await client.post("/gaps", json={"focus": [node_a.id, node_b.id]})
    assert response.status_code == 200
    assert response.json()["gaps"] == []


@pytest.mark.anyio("asyncio")
async def test_openapi_schema_includes_new_routes(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/predict/effects" in schema["paths"]
    assert "/explain" in schema["paths"]
