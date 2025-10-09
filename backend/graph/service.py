"""Graph service utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from ..config import (
    DEFAULT_GRAPH_CONFIG,
    DEFAULT_VECTOR_STORE_CONFIG,
    GraphBackendSettings,
    GraphConfig,
    VectorStoreConfig,
)
from .governance import DataGovernanceRegistry, DataSourceRecord

try:  # pragma: no cover - optional dependency
    from opentelemetry import metrics
except Exception:  # pragma: no cover - optional dependency
    metrics = None  # type: ignore[assignment]
from ..reasoning import CausalEffectEstimator, CausalSummary
from .gap_state import ResearchQueueEntry, ResearchQueueStore
from .gaps import EmbeddingConfig, EmbeddingGapFinder, GapReport, RotatEGapFinder
from .ingest_openalex import OpenAlexClient  # type: ignore
from .models import Edge, Evidence, Node
from .persistence import CompositeGraphStore, GraphFragment, GraphStore, InMemoryGraphStore
from .vector_store import build_vector_store
from .literature import (
    LiteratureAggregator,
    LiteratureClient,
    LiteratureRecord,
    OpenAlexSearch,
    SemanticScholarClient,
)


@dataclass(slots=True)
class EvidenceSummary:
    """Lightweight structure returned to the API layer."""

    edge: Edge
    evidence: List[Evidence]


@dataclass(slots=True)
class SimilarityResult:
    """Embedding similarity result returned by the vector store."""

    node: Node
    score: float
    metadata: Dict[str, object]


class _GraphServiceMetrics:
    """Thin wrapper around optional OpenTelemetry metrics."""

    def __init__(self) -> None:
        self._enabled = False
        if metrics is None:
            return
        try:
            meter = metrics.get_meter(__name__)
            self._queue_events = meter.create_counter(
                "graph.research_queue.events",
                unit="1",
                description="Research queue operations",
            )
            self._evidence_queries = meter.create_counter(
                "graph.evidence.lookups",
                unit="1",
                description="Evidence lookup invocations",
            )
            self._enabled = True
        except Exception:  # pragma: no cover - instrumentation best effort
            self._enabled = False

    def record_queue(self, action: str, *, priority: int | None = None) -> None:
        if not self._enabled:
            return
        attributes = {"action": action}
        if priority is not None:
            attributes["priority"] = float(priority)
        try:
            self._queue_events.add(1, attributes=attributes)
        except Exception:  # pragma: no cover - exporter failures ignored
            return

    def record_lookup(self, subject: str | None, predicate: str | None, object_: str | None) -> None:
        if not self._enabled:
            return
        attributes = {
            "has_subject": "yes" if subject else "no",
            "has_predicate": "yes" if predicate else "no",
            "has_object": "yes" if object_ else "no",
        }
        try:
            self._evidence_queries.add(1, attributes=attributes)
        except Exception:  # pragma: no cover - exporter failures ignored
            return


class GraphService:
    """High-level service exposing evidence and graph queries."""

    def __init__(
        self,
        store: GraphStore | None = None,
        config: GraphConfig | None = None,
        vector_config: VectorStoreConfig | None = None,
        embedding_config: EmbeddingConfig | None = None,
        gap_finder: EmbeddingGapFinder | None = None,
        causal_estimator: CausalEffectEstimator | None = None,
        literature_client: OpenAlexClient | None = None,
        literature: LiteratureAggregator | None = None,
    ) -> None:
        self.config = config or DEFAULT_GRAPH_CONFIG
        self.vector_config = vector_config or DEFAULT_VECTOR_STORE_CONFIG
        if store is not None:
            self.store = store
        else:
            self.store = self._create_store(self.config)
        self._embedding_config = embedding_config or EmbeddingConfig()
        self.vector_store = build_vector_store(self.vector_config)
        if gap_finder is not None:
            self._gap_finder = gap_finder
        else:
            self._gap_finder = RotatEGapFinder(self.store, self._embedding_config, vector_store=self.vector_store)
        self._causal_estimator = causal_estimator or CausalEffectEstimator()
        self._literature_client = literature_client
        self._literature = literature
        self._label_cache: Dict[str, str] = {}
        self._research_queue = ResearchQueueStore()
        self._metrics = _GraphServiceMetrics()
        self._governance = DataGovernanceRegistry()
        self._bootstrap_governance()

    def _create_store(self, config: GraphConfig) -> GraphStore:
        primary = self._create_single_store(config.primary)
        if config.mirrors:
            mirrors = [self._create_single_store(mirror) for mirror in config.mirrors]
            return CompositeGraphStore(primary, mirrors)
        return primary

    def _create_single_store(self, settings: GraphBackendSettings) -> GraphStore:
        backend = settings.normalized_backend()
        if backend == "memory":
            return InMemoryGraphStore()
        if backend == "neo4j":  # pragma: no cover - requires driver
            from .persistence import Neo4jGraphStore

            return Neo4jGraphStore(settings.uri or "", settings.username, settings.password)
        if backend == "arangodb":  # pragma: no cover - requires driver
            from .persistence import ArangoGraphStore

            return ArangoGraphStore(settings.uri or "", settings.username, settings.password, settings.database)
        raise ValueError(f"Unsupported graph backend: {backend}")

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
        self._metrics.record_lookup(subject, predicate, object_)
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
            metadata = dict(candidate.metadata)
            if causal_summary is not None:
                if causal_summary.assumption_graph:
                    metadata.setdefault("assumption_graph", causal_summary.assumption_graph)
                if causal_summary.diagnostics:
                    metadata.setdefault("causal_diagnostics", dict(causal_summary.diagnostics))
            reports.append(
                GapReport(
                    subject=candidate.subject,
                    object=candidate.object,
                    predicate=candidate.predicate,
                    embedding_score=candidate.score,
                    impact_score=candidate.impact,
                    reason=candidate.reason,
                    causal=causal_summary,
                    literature=literature,
                    metadata=metadata,
                )
            )
        return reports

    def summarize_causal(self, treatment: str, outcome: str) -> CausalSummary | None:
        """Expose causal diagnostics for API consumers."""

        return self._summarize_causal(treatment, outcome)

    # ------------------------------------------------------------------
    # Persistence helpers used by ingestion jobs
    # ------------------------------------------------------------------
    def persist(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        self.store.upsert_nodes(nodes)
        self.store.upsert_edges(edges)

    def similarity_search(
        self,
        *,
        node_id: str | None = None,
        vector: Sequence[float] | None = None,
        top_k: int = 5,
    ) -> List[SimilarityResult]:
        if node_id is None and vector is None:
            raise ValueError("Either 'node_id' or 'vector' must be provided")
        namespace = getattr(self._gap_finder, "_vector_namespace", "graph_nodes")
        query_vector: Sequence[float]
        metadata: Dict[str, object] = {}
        if vector is not None:
            query_vector = vector
            metadata["source"] = "request"
        else:
            record = self.vector_store.get(namespace, str(node_id))
            if record is None:
                raise KeyError(node_id)
            query_vector = record.vector
            metadata = dict(record.metadata)
        records = self.vector_store.query(namespace, query_vector, top_k=top_k + (1 if node_id else 0))
        results: List[SimilarityResult] = []
        for candidate in records:
            if node_id and candidate.id == node_id:
                continue
            try:
                node = self.store.get_node(candidate.id)
            except Exception:
                continue
            if node is None:
                continue
            score = candidate.score if candidate.score is not None else 0.0
            merged_meta = dict(metadata)
            merged_meta.update(candidate.metadata or {})
            results.append(SimilarityResult(node=node, score=float(score), metadata=merged_meta))
            if len(results) >= top_k:
                break
        return results

    # ------------------------------------------------------------------
    # Research queue helpers
    # ------------------------------------------------------------------
    def list_research_queue(self) -> List[ResearchQueueEntry]:
        return self._research_queue.list()

    def enqueue_research_item(
        self,
        *,
        subject: str,
        predicate: BiolinkPredicate,
        object_: str,
        reason: str,
        author: str,
        priority: int = 2,
        watchers: Iterable[str] | None = None,
        metadata: Dict[str, object] | None = None,
        assigned_to: str | None = None,
        due_date: datetime | None = None,
        checklist: Iterable[Mapping[str, object]] | None = None,
    ) -> ResearchQueueEntry:
        entry = self._research_queue.enqueue(
            subject=subject,
            predicate=predicate,
            object_=object_,
            reason=reason,
            author=author,
            priority=priority,
            watchers=watchers,
            metadata=metadata,
            assigned_to=assigned_to,
            due_date=due_date,
            checklist=checklist,
        )
        self._metrics.record_queue("enqueue", priority=priority)
        return entry

    def update_research_item(
        self,
        entry_id: str,
        *,
        actor: str,
        status: str | None = None,
        priority: int | None = None,
        add_watchers: Iterable[str] | None = None,
        remove_watchers: Iterable[str] | None = None,
        comment: str | None = None,
        metadata: Dict[str, object] | None = None,
        assigned_to: str | None = None,
        due_date: datetime | None = None,
        checklist: Iterable[Mapping[str, object]] | None = None,
    ) -> ResearchQueueEntry:
        entry = self._research_queue.update(
            entry_id,
            actor=actor,
            status=status,
            priority=priority,
            add_watchers=add_watchers,
            remove_watchers=remove_watchers,
            comment=comment,
            metadata=metadata,
            assigned_to=assigned_to,
            due_date=due_date,
            checklist=checklist,
        )
        self._metrics.record_queue("update", priority=priority if priority is not None else entry.priority)
        return entry

    def list_governance_sources(self) -> List[DataSourceRecord]:
        return self._governance.list()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _summarize_causal(self, subject: str, target: str) -> CausalSummary | None:
        treatment_values, outcome_values, assumptions = self._collect_causal_observations(subject, target)
        if not treatment_values or not outcome_values:
            return None
        return self._causal_estimator.estimate_effect(
            treatment_values,
            outcome_values,
            treatment_name=subject,
            outcome_name=target,
            assumptions=assumptions,
        )

    def _collect_causal_observations(self, subject: str, target: str) -> Tuple[List[float], List[float], Dict[str, object]]:
        treatments: List[float] = []
        outcomes: List[float] = []
        confounders: Set[str] = set()
        mediators: Set[str] = set()
        instruments: Set[str] = set()
        self._ensure_label(subject)
        self._ensure_label(target)
        try:
            node = self.store.get_node(subject)
        except NotImplementedError:  # pragma: no cover - depends on backend
            node = None
        if node is not None:
            self._register_label(subject, node)
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
            else:
                mediators.add(edge.object)
                self._ensure_label(edge.object)
        try:
            incoming_target = self.store.get_edge_evidence(object_=target)
        except NotImplementedError:  # pragma: no cover - depends on backend
            incoming_target = []
        for edge in incoming_target:
            if edge.subject == subject:
                continue
            confounders.add(edge.subject)
            self._ensure_label(edge.subject)
        try:
            incoming_subject = self.store.get_edge_evidence(object_=subject)
        except NotImplementedError:  # pragma: no cover - depends on backend
            incoming_subject = []
        for edge in incoming_subject:
            if edge.subject == target:
                continue
            instruments.add(edge.subject)
            self._ensure_label(edge.subject)
        assumption_graph = self._build_assumption_graph(subject, target, confounders, mediators, instruments)
        labels = {
            node_id: self._label_for_node(node_id)
            for node_id in {subject, target, *confounders, *mediators, *instruments}
        }
        assumptions: Dict[str, object] = {
            "graph": assumption_graph,
            "confounders": sorted(confounders),
            "mediators": sorted(mediators),
            "instruments": sorted(instruments),
            "labels": labels,
        }
        return treatments, outcomes, assumptions

    def _suggest_literature(self, subject: str, target: str, limit: int = 3) -> List[str]:
        aggregation_failed = False
        aggregator = self._ensure_literature_aggregator()
        if aggregator is not None:
            try:
                records = aggregator.suggest(subject, target, limit=limit)
            except Exception:  # pragma: no cover - network dependent
                aggregation_failed = True
            else:
                return [self._format_literature_record(record) for record in records]
        else:
            aggregation_failed = True

        if not aggregation_failed:
            return []

        client = self._ensure_literature_client()
        if client is None:
            return []
        suggestions: List[str] = []
        query = f"{subject} {target}"
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

    def _ensure_label(self, node_id: str) -> None:
        if node_id in self._label_cache:
            return
        try:
            node = self.store.get_node(node_id)
        except NotImplementedError:  # pragma: no cover - depends on backend
            node = None
        self._register_label(node_id, node)

    def _register_label(self, node_id: str, node: Node | None) -> None:
        if node_id in self._label_cache:
            return
        if node is not None and getattr(node, "name", None):
            label = f"{node.name} ({node_id})"
        else:
            label = node_id
        self._label_cache[node_id] = label

    def _label_for_node(self, node_id: str) -> str:
        if node_id not in self._label_cache:
            self._ensure_label(node_id)
        return self._label_cache.get(node_id, node_id)

    def _bootstrap_governance(self) -> None:
        if self._governance.list():
            return
        registry = self._governance
        registry.register("OpenAlex", category="literature", pii=False, retention="standard", access_tier="open")
        registry.update_checks(
            "OpenAlex",
            [
                {"name": "license", "passed": True, "note": "CC-BY"},
                {"name": "ingestion_audit", "passed": True},
            ],
        )
        registry.register("Semantic Scholar", category="literature", pii=False, retention="standard", access_tier="open")
        registry.update_checks(
            "Semantic Scholar",
            [
                {"name": "rate_limit_review", "passed": True},
            ],
        )
        registry.register("Human Connectome Project", category="atlas", pii=False, retention="extended", access_tier="controlled")
        registry.update_checks(
            "Human Connectome Project",
            [
                {"name": "license", "passed": True, "note": "ConnectomeDB"},
                {"name": "pii_screen", "passed": True},
            ],
        )
        registry.register("Julich-Brain", category="atlas", pii=False, retention="extended", access_tier="controlled")
        registry.update_checks(
            "Julich-Brain",
            [
                {"name": "license", "passed": True, "note": "EBRAINS"},
            ],
        )
        registry.register("Allen Brain Atlas", category="atlas", pii=False, retention="standard", access_tier="open")
        registry.update_checks(
            "Allen Brain Atlas",
            [
                {"name": "license", "passed": True, "note": "CC-BY"},
            ],
        )
        registry.register("PDSP Ki", category="assay", pii=False, retention="standard", access_tier="open")
        registry.update_checks(
            "PDSP Ki",
            [
                {"name": "data_use_agreement", "passed": True},
            ],
        )

    def _build_assumption_graph(
        self,
        treatment: str,
        outcome: str,
        confounders: Set[str],
        mediators: Set[str],
        instruments: Set[str],
    ) -> str:
        def quote(value: str) -> str:
            escaped = value.replace("\"", "\\\"")
            return f'"{escaped}"'

        def node_definition(node_id: str, *, latent: bool) -> str:
            label = self._label_for_node(node_id).replace("\"", "\\\"")
            attrs = [f'label="{label}"']
            if latent:
                attrs.append("latent=\"yes\"")
            return f"  {quote(node_id)} [{', '.join(attrs)}];"

        lines: List[str] = ["digraph {"]
        declared: Set[str] = set()

        def declare(node_id: str, *, latent: bool = False) -> None:
            if node_id in declared:
                return
            lines.append(node_definition(node_id, latent=latent))
            declared.add(node_id)

        declare(treatment)
        declare(outcome)
        lines.append(f"  {quote(treatment)} -> {quote(outcome)};")
        for conf in sorted(confounders):
            declare(conf, latent=True)
            lines.append(f"  {quote(conf)} -> {quote(treatment)};")
            lines.append(f"  {quote(conf)} -> {quote(outcome)};")
        for med in sorted(mediators):
            declare(med, latent=True)
            lines.append(f"  {quote(treatment)} -> {quote(med)};")
            lines.append(f"  {quote(med)} -> {quote(outcome)};")
        for inst in sorted(instruments):
            declare(inst, latent=True)
            lines.append(f"  {quote(inst)} -> {quote(treatment)};")
        lines.append("}")
        return "\n".join(lines)

    def _ensure_literature_client(self) -> OpenAlexClient | None:
        if self._literature_client is not None:
            return self._literature_client
        try:
            self._literature_client = OpenAlexClient()
        except Exception:  # pragma: no cover - optional dependency
            self._literature_client = None
        return self._literature_client

    def _ensure_literature_aggregator(self) -> LiteratureAggregator | None:
        if self._literature is not None:
            return self._literature
        try:
            clients: List[LiteratureClient] = []
            openalex_client = self._ensure_literature_client()
            try:
                if openalex_client is not None:
                    clients.append(OpenAlexSearch(openalex_client))
                else:
                    clients.append(OpenAlexSearch())
            except Exception:  # pragma: no cover - optional dependency
                pass
            try:
                clients.append(SemanticScholarClient())
            except Exception:  # pragma: no cover - optional dependency
                pass
            if clients:
                self._literature = LiteratureAggregator(clients=clients)
            else:
                self._literature = LiteratureAggregator()
        except Exception:  # pragma: no cover - optional dependency
            self._literature = None
        return self._literature

    def _format_literature_record(self, record: LiteratureRecord) -> str:
        title = record.title or "Unknown work"
        year = f" ({record.year})" if record.year else ""
        identifier = f" [{record.identifier}]" if record.identifier else ""
        url = f" <{record.url}>" if record.url else ""
        source = f" via {record.source}"
        return f"{title}{year}{identifier}{source}{url}"


__all__ = ["GraphService", "EvidenceSummary"]
