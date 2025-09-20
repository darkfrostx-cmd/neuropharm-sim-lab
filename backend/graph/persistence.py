"""Persistence backends for the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

try:  # pragma: no cover - optional dependency
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - optional dependency
    GraphDatabase = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from arango import ArangoClient
except Exception:  # pragma: no cover - optional dependency
    ArangoClient = None  # type: ignore

from .models import BiolinkPredicate, Edge, Evidence, Node, merge_evidence


@dataclass(slots=True)
class GraphFragment:
    """Subgraph returned by expansion queries."""

    nodes: List[Node]
    edges: List[Edge]


@dataclass(slots=True)
class GraphGap:
    """Potential gap in the knowledge graph."""

    subject: str
    object: str
    reason: str


class GraphStore:
    """Abstract interface for persisting and querying the knowledge graph."""

    def upsert_nodes(self, nodes: Iterable[Node]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def upsert_edges(self, edges: Iterable[Edge]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def get_node(self, node_id: str) -> Node | None:  # pragma: no cover - interface
        raise NotImplementedError

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:  # pragma: no cover - interface
        raise NotImplementedError

    def get_edge_evidence(
        self, subject: str | None = None, predicate: str | None = None, object_: str | None = None
    ) -> List[Edge]:  # pragma: no cover - interface
        raise NotImplementedError

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:  # pragma: no cover - interface
        raise NotImplementedError

    def find_gaps(self, focus_nodes: Sequence[str]) -> List[GraphGap]:  # pragma: no cover - interface
        raise NotImplementedError

    def all_nodes(self) -> Sequence[Node]:  # pragma: no cover - interface
        """Return all nodes stored in the backend."""

        raise NotImplementedError

    def all_edges(self) -> Sequence[Edge]:  # pragma: no cover - interface
        """Return all edges stored in the backend."""

        raise NotImplementedError


class InMemoryGraphStore(GraphStore):
    """Simple in-memory graph store for tests and local development."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[tuple[str, str, str], Edge] = {}

    def upsert_nodes(self, nodes: Iterable[Node]) -> None:
        for node in nodes:
            self._nodes[node.id] = node

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        for edge in edges:
            key = edge.key
            if key in self._edges:
                existing = self._edges[key]
                existing.confidence = edge.confidence or existing.confidence
                existing.publications = sorted(set(existing.publications + edge.publications))
                existing.evidence = merge_evidence(existing.evidence, edge.evidence)
                existing.qualifiers.update(edge.qualifiers)
            else:
                self._edges[key] = edge

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:
        return self._edges.get((subject, predicate, object_))

    def get_edge_evidence(
        self, subject: str | None = None, predicate: str | None = None, object_: str | None = None
    ) -> List[Edge]:
        results: List[Edge] = []
        for (subj, pred, obj), edge in self._edges.items():
            if subject and subj != subject:
                continue
            if predicate and pred != predicate:
                continue
            if object_ and obj != object_:
                continue
            results.append(edge)
        return sorted(results, key=lambda e: (e.subject, e.predicate.value, e.object))

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:
        visited = {node_id}
        frontier = {node_id}
        nodes: Dict[str, Node] = {}
        edges: List[Edge] = []
        for _ in range(depth):
            next_frontier: set[str] = set()
            for key, node in self._nodes.items():
                if key in frontier:
                    nodes[key] = node
            for (subj, _, obj), edge in self._edges.items():
                if subj in frontier or obj in frontier:
                    edges.append(edge)
                    if subj not in visited:
                        next_frontier.add(subj)
                    if obj not in visited:
                        next_frontier.add(obj)
            visited.update(next_frontier)
            frontier = next_frontier
            if len(nodes) >= limit:
                break
        for key in list(nodes):
            if len(nodes) >= limit:
                break
        return GraphFragment(nodes=list(nodes.values())[:limit], edges=edges[: limit * 2])

    def find_gaps(self, focus_nodes: Sequence[str]) -> List[GraphGap]:
        gaps: List[GraphGap] = []
        focus = [node for node in focus_nodes if node in self._nodes]
        for i, subject in enumerate(focus):
            for object_ in focus[i + 1 :]:
                if (subject, BiolinkPredicate.RELATED_TO.value, object_) not in self._edges and (
                    object_, BiolinkPredicate.RELATED_TO.value, subject
                ) not in self._edges:
                    gaps.append(
                        GraphGap(
                            subject=subject,
                            object=object_,
                            reason="No related_to edge connecting the focus nodes.",
                        )
                    )
        return gaps

    def all_nodes(self) -> Sequence[Node]:
        return list(self._nodes.values())

    def all_edges(self) -> Sequence[Edge]:
        return list(self._edges.values())


class Neo4jGraphStore(GraphStore):  # pragma: no cover - requires external service
    """Neo4j-backed store used for production deployments."""

    def __init__(self, uri: str, username: str | None = None, password: str | None = None) -> None:
        if GraphDatabase is None:
            raise ImportError("neo4j driver is not installed")
        self._driver = GraphDatabase.driver(uri, auth=(username, password) if username else None)

    def close(self) -> None:
        self._driver.close()

    def upsert_nodes(self, nodes: Iterable[Node]) -> None:
        cypher = """
        UNWIND $rows AS row
        MERGE (n {id: row.id})
        SET n += row.properties
        """
        payload = [
            {"id": node.id, "properties": {k: v for k, v in node.as_linkml().items() if v is not None}}
            for node in nodes
        ]
        if not payload:
            return
        with self._driver.session() as session:
            session.run(cypher, rows=payload)

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        cypher = """
        UNWIND $rows AS row
        MATCH (s {id: row.subject})
        MATCH (o {id: row.object})
        MERGE (s)-[r:REL {predicate: row.predicate, object: row.object, subject: row.subject}]->(o)
        SET r += row.properties
        """
        payload = [
            {
                "subject": edge.subject,
                "object": edge.object,
                "predicate": edge.predicate.value,
                "properties": {k: v for k, v in edge.as_linkml().items() if k not in {"subject", "object", "predicate"}},
            }
            for edge in edges
        ]
        if not payload:
            return
        with self._driver.session() as session:
            session.run(cypher, rows=payload)

    def get_node(self, node_id: str) -> Node | None:
        raise NotImplementedError("Direct Neo4j queries are handled by the API layer")

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:
        raise NotImplementedError("Direct Neo4j queries are handled by the API layer")

    def get_edge_evidence(self, subject: str | None = None, predicate: str | None = None, object_: str | None = None) -> List[Edge]:
        raise NotImplementedError("Direct Neo4j queries are handled by the API layer")

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:
        raise NotImplementedError("Direct Neo4j queries are handled by the API layer")

    def find_gaps(self, focus_nodes: Sequence[str]) -> List[GraphGap]:
        raise NotImplementedError("Direct Neo4j queries are handled by the API layer")


class ArangoGraphStore(GraphStore):  # pragma: no cover - requires external service
    """ArangoDB-backed graph store."""

    def __init__(self, uri: str, username: str | None = None, password: str | None = None, database: str | None = None) -> None:
        if ArangoClient is None:
            raise ImportError("python-arango is not installed")
        self._client = ArangoClient(hosts=uri)
        self._db = self._client.db(database or "_system", username=username, password=password)
        self._vertex_collection = self._db.collection("nodes")
        self._edge_collection = self._db.collection("edges")

    def upsert_nodes(self, nodes: Iterable[Node]) -> None:
        for node in nodes:
            self._vertex_collection.insert_or_replace({"_key": node.id, **node.as_linkml()})

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        for edge in edges:
            self._edge_collection.insert_or_replace(
                {
                    "_from": f"nodes/{edge.subject}",
                    "_to": f"nodes/{edge.object}",
                    **edge.as_linkml(),
                }
            )

    def get_node(self, node_id: str) -> Node | None:
        raise NotImplementedError

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:
        raise NotImplementedError

    def get_edge_evidence(self, subject: str | None = None, predicate: str | None = None, object_: str | None = None) -> List[Edge]:
        raise NotImplementedError

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:
        raise NotImplementedError

    def find_gaps(self, focus_nodes: Sequence[str]) -> List[GraphGap]:
        raise NotImplementedError
