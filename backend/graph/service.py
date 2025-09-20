"""Graph service utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from ..config import DEFAULT_GRAPH_CONFIG, GraphConfig
from .models import Edge, Evidence, Node
from .persistence import GraphFragment, GraphGap, GraphStore, InMemoryGraphStore


@dataclass(slots=True)
class EvidenceSummary:
    """Lightweight structure returned to the API layer."""

    edge: Edge
    evidence: List[Evidence]


class GraphService:
    """High-level service exposing evidence and graph queries."""

    def __init__(self, store: GraphStore | None = None, config: GraphConfig | None = None) -> None:
        self.config = config or DEFAULT_GRAPH_CONFIG
        if store is not None:
            self.store = store
        else:
            self.store = self._create_store(self.config)

    def _create_store(self, config: GraphConfig) -> GraphStore:
        if config.backend == "memory":
            return InMemoryGraphStore()
        if config.backend == "neo4j":  # pragma: no cover - requires driver
            from .persistence import Neo4jGraphStore

            return Neo4jGraphStore(config.uri or "", config.username, config.password)
        if config.backend == "arangodb":  # pragma: no cover - requires driver
            from .persistence import ArangoGraphStore

            return ArangoGraphStore(config.uri or "", config.username, config.password, config.database)
        raise ValueError(f"Unsupported graph backend: {config.backend}")

    # ------------------------------------------------------------------
    # Evidence lookup utilities
    # ------------------------------------------------------------------
    def get_evidence(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
    ) -> List[EvidenceSummary]:
        edges = self.store.get_edge_evidence(subject=subject, predicate=predicate, object_=object_)
        return [EvidenceSummary(edge=edge, evidence=edge.evidence) for edge in edges]

    # ------------------------------------------------------------------
    # Graph navigation helpers
    # ------------------------------------------------------------------
    def expand(self, node_id: str, depth: int = 1, limit: int = 25) -> GraphFragment:
        return self.store.neighbors(node_id, depth=depth, limit=limit)

    def find_gaps(self, node_ids: Sequence[str]) -> List[GraphGap]:
        return self.store.find_gaps(node_ids)

    # ------------------------------------------------------------------
    # Persistence helpers used by ingestion jobs
    # ------------------------------------------------------------------
    def persist(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        self.store.upsert_nodes(nodes)
        self.store.upsert_edges(edges)


__all__ = ["GraphService", "EvidenceSummary"]
