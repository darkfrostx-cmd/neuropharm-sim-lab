"""Graph service utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from ..config import DEFAULT_GRAPH_CONFIG, GraphConfig
from ..reasoning import CausalEffectEstimator, CausalSummary
from .gaps import EmbeddingConfig, EmbeddingGapFinder, GapReport
from .ingest_openalex import OpenAlexClient  # type: ignore
from .models import Edge, Evidence, Node
from .persistence import GraphFragment, GraphStore, InMemoryGraphStore


@dataclass(slots=True)
class EvidenceSummary:
    """Lightweight structure returned to the API layer."""

    edge: Edge
    evidence: List[Evidence]


class GraphService:
    """High-level service exposing evidence and graph queries."""

    def __init__(
        self,
        store: GraphStore | None = None,
        config: GraphConfig | None = None,
        embedding_config: EmbeddingConfig | None = None,
        gap_finder: EmbeddingGapFinder | None = None,
        causal_estimator: CausalEffectEstimator | None = None,
        literature_client: OpenAlexClient | None = None,
    ) -> None:
        self.config = config or DEFAULT_GRAPH_CONFIG
        if store is not None:
            self.store = store
        else:
            self.store = self._create_store(self.config)
        self._embedding_config = embedding_config or EmbeddingConfig()
        self._gap_finder = gap_finder or EmbeddingGapFinder(self.store, self._embedding_config)
        self._causal_estimator = causal_estimator or CausalEffectEstimator()
        self._literature_client = literature_client

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

    def find_gaps(self, node_ids: Sequence[str], top_k: int = 5) -> List[GapReport]:
        candidates = self._gap_finder.rank_missing_edges(node_ids, top_k=top_k)
        if not candidates:
            return []
        reports: List[GapReport] = []
        for candidate in candidates:
            causal_summary = self._summarize_causal(candidate.subject, candidate.object)
            literature = self._suggest_literature(candidate.subject, candidate.object)
            reports.append(
                GapReport(
                    subject=candidate.subject,
                    object=candidate.object,
                    predicate=candidate.predicate,
                    embedding_score=candidate.score,
                    impact_score=candidate.impact,
                    reason=candidate.reason,
                    causal_effect=causal_summary.effect if causal_summary else None,
                    causal_direction=causal_summary.direction if causal_summary else None,
                    causal_confidence=causal_summary.confidence if causal_summary else None,
                    counterfactual_summary=causal_summary.description if causal_summary else None,
                    literature=literature,
                )
            )
        return reports

    # ------------------------------------------------------------------
    # Persistence helpers used by ingestion jobs
    # ------------------------------------------------------------------
    def persist(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        self.store.upsert_nodes(nodes)
        self.store.upsert_edges(edges)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _summarize_causal(self, subject: str, target: str) -> CausalSummary | None:
        treatment_values, outcome_values = self._collect_causal_observations(subject, target)
        if not treatment_values or not outcome_values:
            return None
        return self._causal_estimator.estimate_effect(
            treatment_values,
            outcome_values,
            treatment_name=subject,
            outcome_name=target,
        )

    def _collect_causal_observations(self, subject: str, target: str) -> tuple[List[float], List[float]]:
        treatments: List[float] = []
        outcomes: List[float] = []
        try:
            node = self.store.get_node(subject)
        except NotImplementedError:  # pragma: no cover - depends on backend
            node = None
        if node is not None:
            samples = node.attributes.get("causal_samples")
            if isinstance(samples, list):
                for sample in samples:
                    if not isinstance(sample, dict):
                        continue
                    if sample.get("target") != target:
                        continue
                    treatments.append(float(sample.get("treatment", sample.get("treatment_value", 0.0))))
                    outcomes.append(float(sample.get("outcome", sample.get("outcome_value", 0.0))))
        try:
            edges = self.store.get_edge_evidence(subject=subject)
        except NotImplementedError:  # pragma: no cover - depends on backend
            edges = []
        for edge in edges:
            qualifier_target = edge.qualifiers.get("target") if edge.qualifiers else None
            if edge.object == target or qualifier_target == target:
                treatment_val = edge.qualifiers.get("treatment_value") if edge.qualifiers else None
                if treatment_val is None:
                    treatment_val = edge.confidence if edge.confidence is not None else 1.0
                outcome_val = None
                if edge.qualifiers:
                    outcome_val = (
                        edge.qualifiers.get("outcome_value")
                        or edge.qualifiers.get("delta")
                        or edge.qualifiers.get("effect")
                    )
                if outcome_val is None:
                    outcome_val = edge.confidence if edge.confidence is not None else 0.0
                treatments.append(float(treatment_val))
                outcomes.append(float(outcome_val))
        return treatments, outcomes

    def _suggest_literature(self, subject: str, target: str, limit: int = 3) -> List[str]:
        client = self._ensure_literature_client()
        if client is None:
            return []
        query = f"{subject} {target}"
        suggestions: List[str] = []
        try:
            for record in client.iter_works(search=query, per_page=limit):
                title = record.get("display_name") or "Unknown work"
                year = record.get("publication_year")
                identifier = record.get("id") or record.get("ids", {}).get("openalex")
                snippet = f"{title} ({year})" if year else title
                if identifier:
                    snippet = f"{snippet} [{identifier}]"
                suggestions.append(snippet)
                if len(suggestions) >= limit:
                    break
        except Exception:  # pragma: no cover - network errors
            return []
        return suggestions

    def _ensure_literature_client(self) -> OpenAlexClient | None:
        if self._literature_client is not None:
            return self._literature_client
        try:
            self._literature_client = OpenAlexClient()
        except Exception:  # pragma: no cover - optional dependency
            self._literature_client = None
        return self._literature_client


__all__ = ["GraphService", "EvidenceSummary"]
