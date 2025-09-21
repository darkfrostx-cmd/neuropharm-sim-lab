"""Integration tests targeting the external graph persistence backends."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Sequence

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api import routes as api_routes
from backend.graph.gaps import GapCandidate
from backend.graph.models import (
    BiolinkEntity,
    BiolinkPredicate,
    Edge,
    Evidence,
    Node,
)
from backend.graph.persistence import (
    ArangoGraphStore,
    CompositeGraphStore,
    GraphStore,
    InMemoryGraphStore,
    Neo4jGraphStore,
)
from backend.graph.service import GraphService
from backend.main import app
from backend.simulation.kg_adapter import GraphBackedReceptorAdapter


NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


class RecordingGraphStore(GraphStore):
    """In-memory mirror used to assert composite replication."""

    def __init__(self) -> None:
        self.delegate = InMemoryGraphStore()
        self.seen_nodes: List[Node] = []
        self.seen_edges: List[Edge] = []

    def upsert_nodes(self, nodes: Iterable[Node]) -> None:
        items = list(nodes)
        self.seen_nodes.extend(items)
        self.delegate.upsert_nodes(items)

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        items = list(edges)
        self.seen_edges.extend(items)
        self.delegate.upsert_edges(items)

    def get_node(self, node_id: str) -> Node | None:
        return self.delegate.get_node(node_id)

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:
        return self.delegate.get_edge(subject, predicate, object_)

    def get_edge_evidence(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
    ) -> List[Edge]:
        return self.delegate.get_edge_evidence(subject=subject, predicate=predicate, object_=object_)

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25):
        return self.delegate.neighbors(node_id, depth=depth, limit=limit)

    def find_gaps(self, focus_nodes: Sequence[str]):
        return self.delegate.find_gaps(focus_nodes)

    def all_nodes(self) -> Sequence[Node]:
        return self.delegate.all_nodes()

    def all_edges(self) -> Sequence[Edge]:
        return self.delegate.all_edges()


def test_composite_store_replicates_writes():
    primary = InMemoryGraphStore()
    mirror = RecordingGraphStore()
    composite = CompositeGraphStore(primary, [mirror])

    nodes = _build_nodes()
    edges = _build_edges()

    composite.upsert_nodes(nodes)
    composite.upsert_edges(edges)

    assert {node.id for node in mirror.seen_nodes} == {node.id for node in nodes}
    assert {edge.key for edge in mirror.seen_edges} == {edge.key for edge in edges}
    assert composite.get_node("HGNC:HTR1A") is not None
    assert mirror.get_node("HGNC:HTR1A") is not None
    assert composite.get_edge("CHEMBL:25", BiolinkPredicate.INTERACTS_WITH.value, "HGNC:HTR1A")


def _build_nodes() -> List[Node]:
    return [
        Node(id="CHEMBL:25", name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE),
        Node(id="HGNC:HTR1A", name="HTR1A", category=BiolinkEntity.GENE),
        Node(id="HGNC:HTR2A", name="HTR2A", category=BiolinkEntity.GENE),
        Node(id="UBERON:0000955", name="Hippocampus", category=BiolinkEntity.BRAIN_REGION),
    ]


def _build_edges() -> List[Edge]:
    return [
        Edge(
            subject="CHEMBL:25",
            predicate=BiolinkPredicate.INTERACTS_WITH,
            object="HGNC:HTR1A",
            confidence=0.82,
            evidence=[Evidence(source="ChEMBL", reference="PMID:1", confidence=0.88)],
            qualifiers={"affinity": 0.83},
            created_at=NOW,
        ),
        Edge(
            subject="CHEMBL:25",
            predicate=BiolinkPredicate.INTERACTS_WITH,
            object="HGNC:HTR2A",
            confidence=0.45,
            evidence=[Evidence(source="ChEMBL", reference="PMID:2", confidence=0.5)],
            created_at=NOW,
        ),
        Edge(
            subject="UBERON:0000955",
            predicate=BiolinkPredicate.EXPRESSES,
            object="HGNC:HTR1A",
            confidence=0.68,
            evidence=[Evidence(source="AllenAtlas", reference="PMID:3", confidence=0.7)],
            qualifiers={"expression": 0.72},
            created_at=NOW,
        ),
        Edge(
            subject="UBERON:0000955",
            predicate=BiolinkPredicate.EXPRESSES,
            object="HGNC:HTR2A",
            confidence=0.32,
            evidence=[Evidence(source="AllenAtlas", reference="PMID:4", confidence=0.35)],
            created_at=NOW,
        ),
        Edge(
            subject="HGNC:HTR1A",
            predicate=BiolinkPredicate.COEXPRESSION_WITH,
            object="HGNC:HTR2A",
            confidence=0.4,
            evidence=[Evidence(source="CoExp", reference="PMID:5", confidence=0.42)],
            qualifiers={"weight": 0.38},
            created_at=NOW,
        ),
    ]


def _node_payload(node: Node) -> Dict[str, object]:
    payload = node.as_linkml()
    payload["id"] = node.id
    return payload


def _edge_payload(edge: Edge) -> Dict[str, object]:
    payload = edge.as_linkml()
    payload["subject"] = edge.subject
    payload["object"] = edge.object
    payload["predicate"] = edge.predicate.value
    return payload


def _neighbor_ids(edges: Sequence[Edge], origin: str, depth: int, limit: int) -> List[str]:
    visited = {origin}
    frontier = {origin}
    collected: List[str] = []
    for _ in range(max(1, depth)):
        next_frontier: set[str] = set()
        for edge in edges:
            if edge.subject in frontier and edge.object not in visited:
                next_frontier.add(edge.object)
            if edge.object in frontier and edge.subject not in visited:
                next_frontier.add(edge.subject)
        next_frontier -= visited
        for identifier in next_frontier:
            if identifier not in collected:
                collected.append(identifier)
        visited.update(next_frontier)
        frontier = next_frontier
        if len(collected) >= limit:
            break
    return collected[: max(0, limit)]


class FakeRecord(dict):
    """Simple mapping mimicking the behaviour of Neo4j records."""


class FakeNeo4jResult:
    def __init__(self, records: Iterable[FakeRecord]) -> None:
        self._records = list(records)

    def single(self) -> FakeRecord | None:
        return self._records[0] if self._records else None

    def __iter__(self):
        return iter(self._records)


class FakeNeo4jSession:
    def __init__(self, nodes: Dict[str, Dict[str, object]], edges: List[Dict[str, object]]) -> None:
        self._nodes = nodes
        self._edges = edges

    def __enter__(self) -> "FakeNeo4jSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - interface compliance
        return None

    def run(self, query: str, **params):
        query = " ".join(query.split())
        if "collect(id) AS neighbor_ids" in query:
            origin = params.get("node_id")
            depth = params.get("depth", 1)
            limit = params.get("limit", 25)
            edge_objs = [_edge_from_doc(doc) for doc in self._edges]
            neighbors = _neighbor_ids(edge_objs, origin, depth, limit)
            return FakeNeo4jResult([FakeRecord({"neighbor_ids": neighbors})])
        if "MATCH (n {id: $id})" in query:
            node = self._nodes.get(params.get("id"))
            return FakeNeo4jResult([FakeRecord({"n": node})] if node else [])
        if "RETURN n.id AS id" in query:
            ids = params.get("ids", [])
            return FakeNeo4jResult([
                FakeRecord({"id": node_id}) for node_id in ids if node_id in self._nodes
            ])
        if "WHERE n.id IN $ids" in query and "RETURN n" in query:
            ids = params.get("ids", [])
            records = [FakeRecord({"n": self._nodes[node_id]}) for node_id in ids if node_id in self._nodes]
            return FakeNeo4jResult(records)
        if "WHERE r.subject = $subject" in query and "r.object = $object" in query:
            subject = params.get("subject")
            predicate = params.get("predicate")
            object_ = params.get("object")
            for edge in self._edges:
                if (
                    edge.get("subject") == subject
                    and edge.get("predicate") == predicate
                    and edge.get("object") == object_
                ):
                    return FakeNeo4jResult([FakeRecord({"r": edge})])
            return FakeNeo4jResult([])
        if "WHERE s.id IN $ids AND o.id IN $ids" in query:
            ids = set(params.get("ids", []))
            records = [
                FakeRecord({"r": edge})
                for edge in self._edges
                if edge.get("subject") in ids and edge.get("object") in ids
            ]
            return FakeNeo4jResult(records)
        if "RETURN r" in query and "ORDER BY r.subject" in query:
            subject = params.get("subject")
            predicate = params.get("predicate")
            object_ = params.get("object")
            filtered = []
            for edge in self._edges:
                if subject is not None and edge.get("subject") != subject:
                    continue
                if predicate is not None and edge.get("predicate") != predicate:
                    continue
                if object_ is not None and edge.get("object") != object_:
                    continue
                filtered.append(edge)
            filtered.sort(key=lambda doc: (doc.get("subject"), doc.get("predicate"), doc.get("object")))
            return FakeNeo4jResult([FakeRecord({"r": edge}) for edge in filtered])
        if "RETURN s.id AS subject" in query:
            ids = set(params.get("ids", []))
            predicate = params.get("predicate")
            records = [
                FakeRecord({"subject": edge.get("subject"), "object": edge.get("object")})
                for edge in self._edges
                if edge.get("predicate") == predicate
                and edge.get("subject") in ids
                and edge.get("object") in ids
            ]
            return FakeNeo4jResult(records)
        return FakeNeo4jResult([])

    def close(self) -> None:  # pragma: no cover - interface compliance
        return None


class FakeNeo4jDriver:
    def __init__(self, nodes: Sequence[Node], edges: Sequence[Edge]) -> None:
        self._nodes = {node.id: _node_payload(node) for node in nodes}
        self._edges = [_edge_payload(edge) for edge in edges]

    def session(self) -> FakeNeo4jSession:
        return FakeNeo4jSession(self._nodes, self._edges)

    def close(self) -> None:  # pragma: no cover - interface compliance
        return None


def _edge_from_doc(document: Dict[str, object]) -> Edge:
    return Edge(
        subject=str(document["subject"]),
        predicate=BiolinkPredicate(str(document["predicate"])),
        object=str(document["object"]),
        relation=str(document.get("relation", "biolink:related_to")),
        knowledge_level=document.get("knowledge_level"),
        confidence=float(document.get("confidence")) if document.get("confidence") is not None else None,
        publications=[str(pub) for pub in document.get("publications", [])],
        evidence=[Evidence(**payload) for payload in document.get("evidence", [])],
        qualifiers=document.get("qualifiers") or {},
        created_at=NOW,
    )


class FakeCollection:
    def __init__(self, documents: Iterable[Dict[str, object]]) -> None:
        self.docs: Dict[str, Dict[str, object]] = {}
        for doc in documents:
            key = str(doc.get("_key") or doc.get("id"))
            self.docs[key] = dict(doc)

    def insert_or_replace(self, document: Dict[str, object]) -> None:
        key = str(document.get("_key") or document.get("id"))
        self.docs[key] = dict(document)


class FakeAQLExecutor:
    def __init__(self, vertices: FakeCollection, edges: FakeCollection) -> None:
        self._vertices = vertices
        self._edges = edges

    def execute(self, query: str, bind_vars: Dict[str, object] | None = None):
        bind_vars = bind_vars or {}
        query = " ".join(query.split())
        if "FILTER doc._key == @id" in query or "FILTER doc.id == @id" in query:
            node_id = str(bind_vars.get("id"))
            doc = self._vertices.docs.get(node_id)
            return [dict(doc)] if doc else []
        if "FILTER edge.subject == @subject" in query and "LIMIT 1" in query:
            subject = bind_vars.get("subject")
            predicate = bind_vars.get("predicate")
            object_ = bind_vars.get("object")
            for doc in self._edges.docs.values():
                if (
                    doc.get("subject") == subject
                    and doc.get("predicate") == predicate
                    and doc.get("object") == object_
                ):
                    return [dict(doc)]
            return []
        if "SORT edge.subject" in query:
            subject = bind_vars.get("subject")
            predicate = bind_vars.get("predicate")
            object_ = bind_vars.get("object")
            docs = []
            for doc in self._edges.docs.values():
                if subject is not None and doc.get("subject") != subject:
                    continue
                if predicate is not None and doc.get("predicate") != predicate:
                    continue
                if object_ is not None and doc.get("object") != object_:
                    continue
                docs.append(dict(doc))
            docs.sort(key=lambda item: (item.get("subject"), item.get("predicate"), item.get("object")))
            return docs
        if "RETURN { nodes: nodes, edges: edgeDocs }" in query:
            node_id = str(bind_vars.get("node_id"))
            depth = int(bind_vars.get("depth", 1))
            limit = int(bind_vars.get("limit", 25))
            edge_limit = int(bind_vars.get("edge_limit", limit * 4))
            edges = [_edge_from_doc(doc) for doc in self._edges.docs.values()]
            neighbors = _neighbor_ids(edges, node_id, depth, limit)
            node_ids = [node_id] + [identifier for identifier in neighbors if identifier != node_id]
            node_docs = [self._vertices.docs[node] for node in node_ids if node in self._vertices.docs]
            edge_docs = [
                dict(doc)
                for doc in self._edges.docs.values()
                if doc.get("subject") in node_ids and doc.get("object") in node_ids
            ][:edge_limit]
            return [{"nodes": node_docs, "edges": edge_docs}]
        if "RETURN { nodes: available, edges: related }" in query:
            ids = [str(identifier) for identifier in bind_vars.get("ids", [])]
            predicate = bind_vars.get("predicate")
            available = [identifier for identifier in ids if identifier in self._vertices.docs]
            related = [
                {"subject": doc.get("subject"), "object": doc.get("object")}
                for doc in self._edges.docs.values()
                if doc.get("predicate") == predicate
                and doc.get("subject") in available
                and doc.get("object") in available
            ]
            return [{"nodes": available, "edges": related}]
        return []


class FakeDatabase:
    def __init__(self, nodes: Sequence[Node], edges: Sequence[Edge]) -> None:
        node_docs = [_node_payload(node) | {"_key": node.id} for node in nodes]
        edge_docs = [
            _edge_payload(edge)
            | {
                "_key": f"{edge.subject}|{edge.predicate.value}|{edge.object}",
                "_from": f"nodes/{edge.subject}",
                "_to": f"nodes/{edge.object}",
            }
            for edge in edges
        ]
        self._nodes = FakeCollection(node_docs)
        self._edges = FakeCollection(edge_docs)
        self.aql = FakeAQLExecutor(self._nodes, self._edges)

    def collection(self, name: str) -> FakeCollection:
        if name == "nodes":
            return self._nodes
        if name == "edges":
            return self._edges
        raise KeyError(name)


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as instance:
        yield instance


@pytest.fixture()
def persistent_backend_services(request):
    nodes = _build_nodes()
    edges = _build_edges()
    backend = request.param
    if backend == "neo4j":
        store = Neo4jGraphStore.__new__(Neo4jGraphStore)  # type: ignore[call-arg]
        store._driver = FakeNeo4jDriver(nodes, edges)
    elif backend == "arangodb":
        store = ArangoGraphStore.__new__(ArangoGraphStore)  # type: ignore[call-arg]
        database = FakeDatabase(nodes, edges)
        store._client = None
        store._db = database
        store._vertex_collection = database.collection("nodes")
        store._edge_collection = database.collection("edges")
    else:  # pragma: no cover - defensive
        raise RuntimeError(f"Unsupported backend {backend}")
    
    class SimpleGapFinder:
        def __init__(self, graph_store):
            self.store = graph_store

        def rank_missing_edges(self, focus_nodes, top_k=5):
            gaps = self.store.find_gaps(focus_nodes)
            candidates: List[GapCandidate] = []
            for gap in gaps[:top_k]:
                candidates.append(
                    GapCandidate(
                        subject=gap.subject,
                        object=gap.object,
                        predicate=BiolinkPredicate.RELATED_TO,
                        score=0.9,
                        impact=1.0,
                        reason=gap.reason,
                    )
                )
            return candidates

    service = GraphService(store=store, gap_finder=SimpleGapFinder(store))
    adapter = GraphBackedReceptorAdapter(service)
    previous_graph_service = api_routes.services.graph_service
    previous_adapter = api_routes.services.receptor_adapter
    previous_references = dict(api_routes.services.receptor_references)
    api_routes.services.configure(graph_service=service, receptor_adapter=adapter)
    adapter.clear_cache()
    yield backend
    api_routes.services.configure(graph_service=previous_graph_service, receptor_adapter=previous_adapter)
    api_routes.services.receptor_references = previous_references


@pytest.fixture()
def anyio_backend():
    return "asyncio"


pytestmark = pytest.mark.anyio("asyncio")


@pytest.mark.parametrize("persistent_backend_services", ["neo4j", "arangodb"], indirect=True)
async def test_persistent_backends_drive_endpoints(persistent_backend_services, client):
    response = await client.post("/evidence/search", json={"object": "HGNC:HTR1A"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["provenance"][0]["source"] in {"ChEMBL", "AllenAtlas"}

    response = await client.post("/graph/expand", json={"node_id": "HGNC:HTR1A", "depth": 1, "limit": 10})
    assert response.status_code == 200
    fragment = response.json()
    assert fragment["centre"] == "HGNC:HTR1A"
    assert any(node["id"] == "HGNC:HTR1A" for node in fragment["nodes"])

    response = await client.post("/explain", json={"receptor": "5HT1A", "direction": "both", "limit": 5})
    assert response.status_code == 200
    explanation = response.json()
    assert explanation["edges"]
    assert explanation["canonical_receptor"] == "5-HT1A"

    response = await client.post("/gaps", json={"focus_nodes": ["HGNC:HTR1A", "HGNC:HTR2A"]})
    assert response.status_code == 200
    gaps = response.json()
    assert gaps["items"]
    first_gap = gaps["items"][0]
    assert first_gap["reason"].startswith("No related_to edge")
    assert "embedding_score" in first_gap
    assert "context_weight" in first_gap["context"]
