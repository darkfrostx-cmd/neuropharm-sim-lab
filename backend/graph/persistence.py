"""Persistence backends for the knowledge graph."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence

try:  # pragma: no cover - optional dependency
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - optional dependency
    GraphDatabase = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from arango import ArangoClient
except Exception:  # pragma: no cover - optional dependency
    ArangoClient = None  # type: ignore

from .models import BiolinkEntity, BiolinkPredicate, Edge, Evidence, Node, merge_evidence


LOGGER = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(entity: Any) -> Dict[str, Any]:
    if entity is None:
        return {}
    if isinstance(entity, dict):
        return dict(entity)
    try:
        return dict(entity)
    except Exception:  # pragma: no cover - defensive fallback
        data: Dict[str, Any] = {}
        if hasattr(entity, "keys"):
            for key in entity.keys():  # type: ignore[attr-defined]
                data[key] = entity[key]
        return data


def _coerce_str_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]


def _coerce_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value.items())  # type: ignore[call-arg]
    return {}


def _parse_category(raw: Any) -> BiolinkEntity:
    if isinstance(raw, BiolinkEntity):
        return raw
    if isinstance(raw, str):
        try:
            return BiolinkEntity(raw)
        except ValueError:  # pragma: no cover - unexpected category
            pass
    return BiolinkEntity.NAMED_THING


def _parse_predicate(raw: Any) -> BiolinkPredicate:
    if isinstance(raw, BiolinkPredicate):
        return raw
    if isinstance(raw, str):
        try:
            return BiolinkPredicate(raw)
        except ValueError:  # pragma: no cover - unexpected predicate
            return BiolinkPredicate.RELATED_TO
    return BiolinkPredicate.RELATED_TO


def _parse_datetime(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:  # pragma: no cover - malformed timestamp
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _node_from_payload(payload: Dict[str, Any]) -> Node | None:
    node_id = payload.get("id") or payload.get("_key")
    if node_id is None:
        return None
    name = payload.get("name") or node_id
    attributes = _coerce_dict(payload.get("attributes"))
    synonyms = _coerce_str_list(payload.get("synonym") or payload.get("synonyms"))
    xrefs = _coerce_str_list(payload.get("xref"))
    return Node(
        id=str(node_id),
        name=str(name),
        category=_parse_category(payload.get("category")),
        description=payload.get("description"),
        provided_by=payload.get("provided_by"),
        synonyms=synonyms,
        xrefs=xrefs,
        attributes=attributes,
    )


def _edge_from_payload(payload: Dict[str, Any]) -> Edge | None:
    subject = payload.get("subject")
    if subject is None and payload.get("_from"):
        subject = str(payload["_from"]).split("/", 1)[-1]
    object_ = payload.get("object")
    if object_ is None and payload.get("_to"):
        object_ = str(payload["_to"]).split("/", 1)[-1]
    if subject is None or object_ is None:
        return None
    predicate = _parse_predicate(payload.get("predicate"))
    publications = _coerce_str_list(payload.get("publications"))
    qualifiers_raw = _coerce_dict(payload.get("qualifiers"))
    qualifiers = {str(key): value for key, value in qualifiers_raw.items()}
    evidence_items: List[Evidence] = []
    for raw in payload.get("evidence", []) or []:
        if not isinstance(raw, dict):
            continue
        source = raw.get("source")
        if not source:
            continue
        annotations = _coerce_dict(raw.get("annotations"))
        evidence_items.append(
            Evidence(
                source=str(source),
                reference=raw.get("reference"),
                confidence=_safe_float(raw.get("confidence")),
                uncertainty=raw.get("uncertainty"),
                annotations=annotations,
            )
        )
    created_at = _parse_datetime(payload.get("created_at"))
    return Edge(
        subject=str(subject),
        predicate=predicate,
        object=str(object_),
        relation=str(payload.get("relation", "biolink:related_to")),
        knowledge_level=payload.get("knowledge_level"),
        confidence=_safe_float(payload.get("confidence")),
        publications=publications,
        evidence=evidence_items,
        qualifiers=qualifiers,
        created_at=created_at,
    )


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


class CompositeGraphStore(GraphStore):
    """Replicate writes to multiple stores while reading from the primary."""

    def __init__(self, primary: GraphStore, mirrors: Sequence[GraphStore]) -> None:
        if not mirrors:
            raise ValueError("CompositeGraphStore requires at least one mirror store")
        self.primary = primary
        self.mirrors = list(mirrors)

    def upsert_nodes(self, nodes: Iterable[Node]) -> None:
        materialized = list(nodes)
        if not materialized:
            return
        self.primary.upsert_nodes(materialized)
        for mirror in self.mirrors:
            try:
                mirror.upsert_nodes(materialized)
            except Exception as exc:  # pragma: no cover - dependent on remote service
                LOGGER.warning("Mirror %s failed to upsert nodes: %s", mirror.__class__.__name__, exc)

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        materialized = list(edges)
        if not materialized:
            return
        self.primary.upsert_edges(materialized)
        for mirror in self.mirrors:
            try:
                mirror.upsert_edges(materialized)
            except Exception as exc:  # pragma: no cover - dependent on remote service
                LOGGER.warning("Mirror %s failed to upsert edges: %s", mirror.__class__.__name__, exc)

    def get_node(self, node_id: str) -> Node | None:
        return self.primary.get_node(node_id)

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:
        return self.primary.get_edge(subject, predicate, object_)

    def get_edge_evidence(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
    ) -> List[Edge]:
        return self.primary.get_edge_evidence(subject=subject, predicate=predicate, object_=object_)

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:
        return self.primary.neighbors(node_id, depth=depth, limit=limit)

    def find_gaps(self, focus_nodes: Sequence[str]) -> List[GraphGap]:
        return self.primary.find_gaps(focus_nodes)

    def all_nodes(self) -> Sequence[Node]:
        return self.primary.all_nodes()

    def all_edges(self) -> Sequence[Edge]:
        return self.primary.all_edges()


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
        cypher = """
        MATCH (n {id: $id})
        RETURN n
        LIMIT 1
        """
        with self._driver.session() as session:
            record = session.run(cypher, id=node_id).single()
        if not record:
            return None
        payload = _as_dict(record.get("n"))
        node = _node_from_payload(payload)
        return node

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:
        cypher = """
        MATCH ()-[r:REL]->()
        WHERE r.subject = $subject AND r.predicate = $predicate AND r.object = $object
        RETURN r
        LIMIT 1
        """
        with self._driver.session() as session:
            record = session.run(cypher, subject=subject, predicate=predicate, object=object_).single()
        if not record:
            return None
        payload = _as_dict(record.get("r"))
        edge = _edge_from_payload(payload)
        return edge

    def get_edge_evidence(self, subject: str | None = None, predicate: str | None = None, object_: str | None = None) -> List[Edge]:
        filters: List[str] = []
        params: Dict[str, Any] = {}
        if subject is not None:
            filters.append("r.subject = $subject")
            params["subject"] = subject
        if predicate is not None:
            filters.append("r.predicate = $predicate")
            params["predicate"] = predicate
        if object_ is not None:
            filters.append("r.object = $object")
            params["object"] = object_
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        cypher = f"""
        MATCH ()-[r:REL]->()
        {where_clause}
        RETURN r
        ORDER BY r.subject, r.predicate, r.object
        """
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            edges: List[Edge] = []
            for record in result:
                payload = _as_dict(record.get("r"))
                edge = _edge_from_payload(payload)
                if edge is not None:
                    edges.append(edge)
        return edges

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:
        centre = self.get_node(node_id)
        if centre is None:
            return GraphFragment(nodes=[], edges=[])
        neighbor_ids: List[str] = []
        with self._driver.session() as session:
            cypher_ids = """
            MATCH (start {id: $node_id})
            CALL {
                WITH start
                MATCH path=(start)-[:REL*1..$depth]-(neighbor)
                RETURN DISTINCT neighbor.id AS id
                LIMIT $limit
            }
            RETURN collect(id) AS neighbor_ids
            """
            record = session.run(
                cypher_ids,
                node_id=node_id,
                depth=max(1, depth),
                limit=max(0, limit),
            ).single()
            if record:
                neighbor_ids = [str(value) for value in record.get("neighbor_ids", []) if value]
            node_ids = [centre.id]
            for identifier in neighbor_ids:
                if identifier not in node_ids:
                    node_ids.append(identifier)
            node_ids = node_ids[: max(1, limit)]
            nodes_query = """
            MATCH (n)
            WHERE n.id IN $ids
            RETURN n
            """
            nodes: Dict[str, Node] = {}
            for record in session.run(nodes_query, ids=node_ids):
                payload = _as_dict(record.get("n"))
                node = _node_from_payload(payload)
                if node is not None:
                    nodes[node.id] = node
            if centre.id not in nodes:
                nodes[centre.id] = centre
            edge_query = """
            MATCH (s)-[r:REL]->(o)
            WHERE s.id IN $ids AND o.id IN $ids
            RETURN r
            """
            edges: List[Edge] = []
            edge_limit = max(1, limit) * 4
            for record in session.run(edge_query, ids=list(nodes.keys())):
                payload = _as_dict(record.get("r"))
                edge = _edge_from_payload(payload)
                if edge is not None:
                    edges.append(edge)
            edges = edges[:edge_limit]
        ordered_nodes = [nodes[node_id] for node_id in node_ids if node_id in nodes]
        if centre.id not in {node.id for node in ordered_nodes}:
            ordered_nodes.insert(0, nodes[centre.id])
        return GraphFragment(nodes=ordered_nodes, edges=edges)

    def find_gaps(self, focus_nodes: Sequence[str]) -> List[GraphGap]:
        if not focus_nodes:
            return []
        unique_ids = list(dict.fromkeys(focus_nodes))
        with self._driver.session() as session:
            node_query = """
            MATCH (n)
            WHERE n.id IN $ids
            RETURN n.id AS id
            """
            existing = {str(record.get("id")) for record in session.run(node_query, ids=unique_ids)}
            filtered = [identifier for identifier in unique_ids if identifier in existing]
            if len(filtered) < 2:
                return []
            edge_query = """
            MATCH (s)-[r:REL]->(o)
            WHERE s.id IN $ids AND o.id IN $ids AND r.predicate = $predicate
            RETURN s.id AS subject, o.id AS object
            """
            predicate = BiolinkPredicate.RELATED_TO.value
            connected = {
                (str(record.get("subject")), str(record.get("object")))
                for record in session.run(edge_query, ids=filtered, predicate=predicate)
            }
        gaps: List[GraphGap] = []
        for i, subject in enumerate(filtered):
            for object_ in filtered[i + 1 :]:
                if (subject, object_) in connected or (object_, subject) in connected:
                    continue
                gaps.append(
                    GraphGap(
                        subject=subject,
                        object=object_,
                        reason="No related_to edge connecting the focus nodes.",
                    )
                    )
        return gaps

    def all_nodes(self) -> Sequence[Node]:
        cypher = """
        MATCH (n)
        RETURN n
        """
        with self._driver.session() as session:
            result = session.run(cypher)
            nodes: List[Node] = []
            for record in result:
                payload = _as_dict(record.get("n"))
                node = _node_from_payload(payload)
                if node is not None:
                    nodes.append(node)
        return nodes

    def all_edges(self) -> Sequence[Edge]:
        cypher = """
        MATCH ()-[r:REL]->()
        RETURN r
        """
        with self._driver.session() as session:
            result = session.run(cypher)
            edges: List[Edge] = []
            for record in result:
                payload = _as_dict(record.get("r"))
                edge = _edge_from_payload(payload)
                if edge is not None:
                    edges.append(edge)
        return edges


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
        query = """
        FOR doc IN nodes
            FILTER doc._key == @id OR doc.id == @id
            LIMIT 1
            RETURN doc
        """
        cursor = self._db.aql.execute(query, bind_vars={"id": node_id})
        for document in cursor:
            node = _node_from_payload(dict(document))
            if node is not None:
                return node
        return None

    def get_edge(self, subject: str, predicate: str, object_: str) -> Edge | None:
        query = """
        FOR edge IN edges
            FILTER edge.subject == @subject AND edge.predicate == @predicate AND edge.object == @object
            LIMIT 1
            RETURN edge
        """
        cursor = self._db.aql.execute(
            query,
            bind_vars={"subject": subject, "predicate": predicate, "object": object_},
        )
        for document in cursor:
            edge = _edge_from_payload(dict(document))
            if edge is not None:
                return edge
        return None

    def get_edge_evidence(self, subject: str | None = None, predicate: str | None = None, object_: str | None = None) -> List[Edge]:
        query = """
        FOR edge IN edges
            FILTER (@subject == null OR edge.subject == @subject)
                AND (@predicate == null OR edge.predicate == @predicate)
                AND (@object == null OR edge.object == @object)
            SORT edge.subject, edge.predicate, edge.object
            RETURN edge
        """
        cursor = self._db.aql.execute(
            query,
            bind_vars={"subject": subject, "predicate": predicate, "object": object_},
        )
        results: List[Edge] = []
        for document in cursor:
            edge = _edge_from_payload(dict(document))
            if edge is not None:
                results.append(edge)
        return results

    def neighbors(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:
        centre = self.get_node(node_id)
        if centre is None:
            return GraphFragment(nodes=[], edges=[])
        query = """
        LET start = DOCUMENT(CONCAT('nodes/', @node_id))
        FILTER start != null
        LET traversed = (
            FOR v, e IN 1..@depth ANY CONCAT('nodes/', @node_id) edges
                OPTIONS { bfs: true, uniqueVertices: "path" }
                LIMIT @limit
                RETURN v
        )
        LET nodes = UNIQUE(APPEND([start], traversed))
        LET nodeIds = nodes[*].id
        LET edgeDocs = (
            FOR edge IN edges
                FILTER edge.subject IN nodeIds AND edge.object IN nodeIds
                LIMIT @edge_limit
                RETURN edge
        )
        RETURN { nodes: nodes, edges: edgeDocs }
        """
        cursor = self._db.aql.execute(
            query,
            bind_vars={
                "node_id": node_id,
                "depth": max(1, depth),
                "limit": max(0, limit),
                "edge_limit": max(1, limit) * 4,
            },
        )
        fragment_nodes: Dict[str, Node] = {centre.id: centre}
        fragment_edges: List[Edge] = []
        for document in cursor:
            data = dict(document)
            for node_doc in data.get("nodes", []):
                node = _node_from_payload(dict(node_doc))
                if node is not None:
                    fragment_nodes[node.id] = node
            for edge_doc in data.get("edges", []):
                edge = _edge_from_payload(dict(edge_doc))
                if edge is not None:
                    fragment_edges.append(edge)
        ordered_ids = [centre.id]
        for identifier in fragment_nodes:
            if identifier != centre.id:
                ordered_ids.append(identifier)
        ordered_ids = ordered_ids[: max(1, limit)]
        nodes = [fragment_nodes[node_id] for node_id in ordered_ids if node_id in fragment_nodes]
        return GraphFragment(nodes=nodes, edges=fragment_edges[: max(1, limit) * 4])

    def find_gaps(self, focus_nodes: Sequence[str]) -> List[GraphGap]:
        if not focus_nodes:
            return []
        query = """
        LET available = (
            FOR identifier IN @ids
                LET doc = DOCUMENT(CONCAT('nodes/', identifier))
                FILTER doc != null
                RETURN doc.id
        )
        LET related = (
            FOR edge IN edges
                FILTER edge.subject IN available
                    AND edge.object IN available
                    AND edge.predicate == @predicate
                RETURN { subject: edge.subject, object: edge.object }
        )
        RETURN { nodes: available, edges: related }
        """
        cursor = self._db.aql.execute(
            query,
            bind_vars={
                "ids": list(dict.fromkeys(focus_nodes)),
                "predicate": BiolinkPredicate.RELATED_TO.value,
            },
        )
        available: List[str] = []
        connected: set[tuple[str, str]] = set()
        for document in cursor:
            data = dict(document)
            available = [str(identifier) for identifier in data.get("nodes", []) if identifier]
            connected = {
                (str(entry.get("subject")), str(entry.get("object")))
                for entry in data.get("edges", [])
                if entry.get("subject") and entry.get("object")
            }
        if len(available) < 2:
            return []
        gaps: List[GraphGap] = []
        for i, subject in enumerate(available):
            for object_ in available[i + 1 :]:
                if (subject, object_) in connected or (object_, subject) in connected:
                    continue
                gaps.append(
                    GraphGap(
                        subject=subject,
                        object=object_,
                        reason="No related_to edge connecting the focus nodes.",
                    )
                )
        return gaps

    def all_nodes(self) -> Sequence[Node]:
        cursor = self._db.aql.execute("FOR doc IN nodes RETURN doc")
        nodes: List[Node] = []
        for document in cursor:
            node = _node_from_payload(dict(document))
            if node is not None:
                nodes.append(node)
        return nodes

    def all_edges(self) -> Sequence[Edge]:
        cursor = self._db.aql.execute("FOR edge IN edges RETURN edge")
        edges: List[Edge] = []
        for document in cursor:
            edge = _edge_from_payload(dict(document))
            if edge is not None:
                edges.append(edge)
        return edges
