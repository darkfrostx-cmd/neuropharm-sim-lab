"""Gap detection utilities leveraging lightweight knowledge graph embeddings.

The functions exposed here intentionally avoid heavyweight dependencies such as
PyKEEN.  They provide a small TransE/RotatE-inspired embedding that can be
trained directly against the :class:`~backend.graph.persistence.GraphStore`
interface.  The resulting scores are used to rank plausible yet missing edges
between a set of focus nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

from ..reasoning import CausalSummary, CounterfactualScenario
from .models import BiolinkPredicate, Edge, Node
from .persistence import GraphStore
from .vector_store import BaseVectorStore, InMemoryVectorStore, VectorRecord


@dataclass(slots=True)
class EmbeddingConfig:
    """Configuration for the lightweight embedding trainer."""

    embedding_dim: int = 32
    learning_rate: float = 0.02
    epochs: int = 150
    negative_ratio: int = 2
    regularization: float = 1e-3
    seed: int = 13
    margin: float = 6.0


@dataclass(slots=True)
class GapCandidate:
    """Potential missing edge predicted by the embedding model."""

    subject: str
    object: str
    predicate: BiolinkPredicate
    score: float
    impact: float
    reason: str = "Embedding model highlighted this relation as a likely gap."
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class GapReport:
    """Structured report shared with the API layer."""

    subject: str
    object: str
    predicate: BiolinkPredicate
    embedding_score: float
    impact_score: float
    reason: str
    causal: CausalSummary | None = None
    literature: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    @property
    def causal_effect(self) -> float | None:
        return self.causal.effect if self.causal else None

    @property
    def causal_direction(self) -> str | None:
        return self.causal.direction if self.causal else None

    @property
    def causal_confidence(self) -> float | None:
        return self.causal.confidence if self.causal else None

    @property
    def counterfactual_summary(self) -> str | None:
        return self.causal.description if self.causal else None

    @property
    def counterfactuals(self) -> List[CounterfactualScenario]:
        return list(self.causal.counterfactuals) if self.causal else []

    @property
    def assumption_graph(self) -> str | None:
        return self.causal.assumption_graph if self.causal else None


class RotatEGapFinder:
    """Train and query a simple TransE-like embedding over the graph."""

    def __init__(
        self,
        store: GraphStore,
        config: EmbeddingConfig | None = None,
        vector_store: BaseVectorStore | None = None,
    ) -> None:
        self.store = store
        self.config = config or EmbeddingConfig()
        self._vector_store = vector_store or InMemoryVectorStore()
        self._node_index: Dict[str, int] = {}
        self._relation_index: Dict[BiolinkPredicate, int] = {}
        self._entity_embeddings: np.ndarray | None = None
        self._relation_embeddings: np.ndarray | None = None
        self._snapshot: Tuple[int, int] | None = None
        self._vector_namespace = "graph_nodes"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def rank_missing_edges(self, focus_nodes: Sequence[str], top_k: int = 5) -> List[GapCandidate]:
        """Return the highest impact missing edges touching the focus nodes."""

        self._ensure_model()
        if self._entity_embeddings is None or self._relation_embeddings is None:
            return []

        nodes = {node.id: node for node in self._iter_nodes()}
        focus_targets = set(focus_nodes)
        edges = list(self._iter_edges())
        existing = {(edge.subject, edge.predicate.value, edge.object) for edge in edges}
        existing_pairs = self._existing_pair(existing)
        degrees = self._compute_degrees(edges)
        context = self._collect_context(edges)
        candidates: List[GapCandidate] = []
        for subject in focus_nodes:
            if subject not in self._node_index:
                continue
            candidate_ids = self._candidate_nodes(subject, nodes.keys())
            for node_id in candidate_ids:
                if node_id == subject:
                    continue
                if (subject, node_id) not in existing_pairs:
                    best = self._best_predicate(subject, node_id)
                    if best is None:
                        continue
                    predicate, raw_score = best
                    context_weight, context_label, context_uncertainty = self._contextual_weight(subject, node_id, context)
                    adjusted_score = raw_score * context_weight
                    impact = self._impact_score(
                        adjusted_score,
                        degrees.get(subject, 0),
                        degrees.get(node_id, 0),
                        context_uncertainty,
                    )
                    if node_id in focus_targets:
                        impact /= 1.5
                    metadata = {
                        "degree_sum": float(degrees.get(subject, 0) + degrees.get(node_id, 0)),
                        "context_weight": float(context_weight),
                        "raw_score": float(raw_score),
                        "context_uncertainty": float(context_uncertainty),
                    }
                    default_reason = GapCandidate.__dataclass_fields__["reason"].default
                    reason = str(default_reason)
                    metadata["context_label"] = context_label or ""
                    if context_label:
                        reason = f"{reason} Context: {context_label}."
                    candidates.append(
                        GapCandidate(
                            subject=subject,
                            object=node_id,
                            predicate=predicate,
                            score=adjusted_score,
                            impact=impact,
                            reason=reason,
                            metadata=metadata,
                        )
                    )
        candidates.sort(key=lambda candidate: candidate.impact, reverse=True)
        return candidates[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_model(self) -> None:
        nodes = list(self._iter_nodes())
        edges = list(self._iter_edges())
        snapshot = (len(nodes), len(edges))
        if self._entity_embeddings is not None and self._relation_embeddings is not None and snapshot == self._snapshot:
            return
        if not nodes or not edges:
            self._entity_embeddings = None
            self._relation_embeddings = None
            self._snapshot = snapshot
            return
        self._prepare_indices(nodes, edges)
        self._train_model(edges)
        self._persist_embeddings()
        self._snapshot = snapshot

    def _iter_nodes(self) -> Iterable[Node]:
        try:
            return self.store.all_nodes()
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError("Graph store cannot enumerate nodes") from exc

    def _iter_edges(self) -> Iterable[Edge]:
        try:
            return self.store.all_edges()
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError("Graph store cannot enumerate edges") from exc

    def _prepare_indices(self, nodes: Sequence[Node], edges: Sequence[Edge]) -> None:
        self._node_index = {node.id: idx for idx, node in enumerate(nodes)}
        unique_predicates = {edge.predicate for edge in edges}
        self._relation_index = {predicate: idx for idx, predicate in enumerate(sorted(unique_predicates, key=lambda p: p.value))}
        rng = np.random.default_rng(self.config.seed)
        entity_phases = rng.uniform(0.0, 2.0 * math.pi, size=(len(self._node_index), self.config.embedding_dim))
        relation_phases = rng.uniform(0.0, 2.0 * math.pi, size=(len(self._relation_index), self.config.embedding_dim))
        self._entity_embeddings = np.exp(1j * entity_phases).astype(np.complex64)
        self._relation_embeddings = np.exp(1j * relation_phases).astype(np.complex64)

    def _train_model(self, edges: Sequence[Edge]) -> None:
        if self._entity_embeddings is None or self._relation_embeddings is None:
            return
        triples = self._edges_to_triples(edges)
        if not triples:
            return
        rng = np.random.default_rng(self.config.seed)
        lr = self.config.learning_rate
        reg = self.config.regularization
        for _ in range(self.config.epochs):
            rng.shuffle(triples)
            for subject_idx, predicate_idx, object_idx in triples:
                self._apply_positive_update(subject_idx, predicate_idx, object_idx, lr, reg)
                for _ in range(self.config.negative_ratio):
                    negative_idx = rng.integers(0, self._entity_embeddings.shape[0])
                    if negative_idx == object_idx:
                        continue
                    self._apply_negative_update(subject_idx, predicate_idx, negative_idx, lr, reg)

    def _edges_to_triples(self, edges: Sequence[Edge]) -> List[Tuple[int, int, int]]:
        triples: List[Tuple[int, int, int]] = []
        for edge in edges:
            subj_idx = self._node_index.get(edge.subject)
            obj_idx = self._node_index.get(edge.object)
            pred_idx = self._relation_index.get(edge.predicate)
            if subj_idx is None or obj_idx is None or pred_idx is None:
                continue
            triples.append((subj_idx, pred_idx, obj_idx))
        return triples

    def _apply_positive_update(self, subject_idx: int, predicate_idx: int, object_idx: int, lr: float, reg: float) -> None:
        assert self._entity_embeddings is not None and self._relation_embeddings is not None
        subject_vec = self._entity_embeddings[subject_idx]
        relation_vec = self._relation_embeddings[predicate_idx]
        object_vec = self._entity_embeddings[object_idx]
        predicted = subject_vec * relation_vec
        diff = predicted - object_vec
        updated_subject = subject_vec - lr * diff * np.conjugate(relation_vec)
        updated_relation = relation_vec - lr * diff * np.conjugate(subject_vec)
        updated_object = object_vec + lr * diff
        self._entity_embeddings[subject_idx] = self._normalize_entity(updated_subject, reg)
        self._relation_embeddings[predicate_idx] = self._normalize_relation(updated_relation)
        self._entity_embeddings[object_idx] = self._normalize_entity(updated_object, reg)

    def _apply_negative_update(self, subject_idx: int, predicate_idx: int, object_idx: int, lr: float, reg: float) -> None:
        assert self._entity_embeddings is not None and self._relation_embeddings is not None
        subject_vec = self._entity_embeddings[subject_idx]
        relation_vec = self._relation_embeddings[predicate_idx]
        object_vec = self._entity_embeddings[object_idx]
        predicted = subject_vec * relation_vec
        diff = predicted - object_vec
        updated_subject = subject_vec + lr * diff * np.conjugate(relation_vec)
        updated_relation = relation_vec + lr * diff * np.conjugate(subject_vec)
        updated_object = object_vec - lr * diff
        self._entity_embeddings[subject_idx] = self._normalize_entity(updated_subject, reg)
        self._relation_embeddings[predicate_idx] = self._normalize_relation(updated_relation)
        self._entity_embeddings[object_idx] = self._normalize_entity(updated_object, reg)

    def _existing_pair(self, existing: set[Tuple[str, str, str]]) -> set[Tuple[str, str]]:
        return {(subject, obj) for subject, _, obj in existing}

    def _best_predicate(self, subject: str, object_: str) -> Tuple[BiolinkPredicate, float] | None:
        if self._entity_embeddings is None or self._relation_embeddings is None:
            return None
        subj_idx = self._node_index.get(subject)
        obj_idx = self._node_index.get(object_)
        if subj_idx is None or obj_idx is None:
            return None
        best_score = -math.inf
        best_predicate: BiolinkPredicate | None = None
        for predicate, idx in self._relation_index.items():
            score = self._score(subj_idx, idx, obj_idx)
            if score > best_score:
                best_score = score
                best_predicate = predicate
        if best_predicate is None:
            return None
        return best_predicate, best_score

    def _score(self, subject_idx: int, predicate_idx: int, object_idx: int) -> float:
        assert self._entity_embeddings is not None and self._relation_embeddings is not None
        subject_vec = self._entity_embeddings[subject_idx]
        predicate_vec = self._relation_embeddings[predicate_idx]
        object_vec = self._entity_embeddings[object_idx]
        predicted = subject_vec * predicate_vec
        distance = np.linalg.norm(predicted - object_vec)
        return float(-distance)

    def _candidate_nodes(self, subject: str, node_ids: Iterable[str]) -> List[str]:
        if self._entity_embeddings is None:
            return list(node_ids)
        subj_idx = self._node_index.get(subject)
        if subj_idx is None:
            return list(node_ids)
        query_vector = self._complex_to_real(self._entity_embeddings[subj_idx])
        try:
            records = self._vector_store.query(self._vector_namespace, query_vector, top_k=64)
        except Exception:
            records = []
        ordered: List[str] = []
        seen: set[str] = set()
        for record in records:
            node_id = record.metadata.get("node_id") if isinstance(record.metadata, dict) else record.id
            if not isinstance(node_id, str):
                node_id = record.id
            if node_id in self._node_index and node_id not in seen:
                ordered.append(node_id)
                seen.add(node_id)
        for node_id in node_ids:
            if node_id not in seen:
                ordered.append(node_id)
        return ordered

    def _persist_embeddings(self) -> None:
        if self._entity_embeddings is None:
            return
        try:
            self._vector_store.delete_namespace(self._vector_namespace)
        except Exception:
            pass
        records: List[VectorRecord] = []
        for node_id, idx in self._node_index.items():
            vector = self._complex_to_real(self._entity_embeddings[idx])
            records.append(VectorRecord(id=node_id, vector=vector, metadata={"node_id": node_id}))
        try:
            self._vector_store.upsert(self._vector_namespace, records)
        except Exception:
            pass

    def _complex_to_real(self, embedding: np.ndarray) -> Tuple[float, ...]:
        real = np.real(embedding)
        imag = np.imag(embedding)
        combined = np.concatenate([real, imag])
        return tuple(float(value) for value in combined)

    def _impact_score(self, embedding_score: float, subject_degree: int, object_degree: int, uncertainty: float) -> float:
        degree_factor = math.log(2 + subject_degree + object_degree)
        magnitude = abs(embedding_score)
        uncertainty_factor = 0.6 + 0.4 * float(max(0.0, min(1.0, uncertainty)))
        return magnitude * degree_factor * uncertainty_factor

    @staticmethod
    def _compute_degrees(edges: Sequence[Edge]) -> Dict[str, int]:
        degrees: Dict[str, int] = {}
        for edge in edges:
            degrees[edge.subject] = degrees.get(edge.subject, 0) + 1
            degrees[edge.object] = degrees.get(edge.object, 0) + 1
        return degrees

    def _normalize_entity(self, vector: np.ndarray, reg: float) -> np.ndarray:
        vector = vector * (1.0 - reg)
        norms = np.abs(vector)
        mask = norms > 1.0
        if np.any(mask):
            vector = vector.copy()
            vector[mask] = vector[mask] / norms[mask]
        return vector.astype(np.complex64)

    def _normalize_relation(self, vector: np.ndarray) -> np.ndarray:
        phases = np.angle(vector)
        return np.exp(1j * phases).astype(np.complex64)

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------
    def _collect_context(self, edges: Sequence[Edge]) -> Dict[str, Dict[str, object]]:
        context: Dict[str, Dict[str, object]] = {}

        def _entry(identifier: str) -> Dict[str, object]:
            return context.setdefault(
                identifier,
                {
                    "species": set(),
                    "timecourse": set(),
                    "regions": set(),
                    "behaviors": set(),
                    "confidence": [],
                },
            )

        for edge in edges:
            qualifiers = edge.qualifiers or {}
            species = self._normalize_to_set(
                qualifiers.get("species")
                or qualifiers.get("species_name")
                or qualifiers.get("taxon")
                or qualifiers.get("species_id")
            )
            timecourse = self._normalize_to_set(
                qualifiers.get("timecourse")
                or qualifiers.get("chronicity")
                or qualifiers.get("duration")
            )
            regions = self._normalize_to_set(
                qualifiers.get("region") or qualifiers.get("brain_region") or qualifiers.get("anatomy")
            )
            behaviours = self._normalize_to_set(qualifiers.get("behaviour") or qualifiers.get("behavior_tag"))

            for node_id in (edge.subject, edge.object):
                entry = _entry(node_id)
                entry["species"].update(species)
                entry["timecourse"].update(timecourse)
                entry["regions"].update(regions)
                entry["behaviors"].update(behaviours)
                if edge.confidence is not None:
                    entry["confidence"].append(float(edge.confidence))
                for evidence in edge.evidence:
                    annotations = getattr(evidence, "annotations", {})
                    if not isinstance(annotations, dict):
                        continue
                    entry["species"].update(self._normalize_to_set(annotations.get("species")))
                    entry["timecourse"].update(self._normalize_to_set(annotations.get("timecourse")))
                    entry["regions"].update(self._normalize_to_set(annotations.get("region")))
                    entry["behaviors"].update(self._normalize_to_set(annotations.get("behavior")))
                    conf = annotations.get("confidence")
                    if conf is not None:
                        try:
                            entry["confidence"].append(float(conf))
                        except (TypeError, ValueError):  # pragma: no cover - defensive
                            pass
        return context

    def _contextual_weight(
        self,
        subject: str,
        object_: str,
        context: Mapping[str, Dict[str, object]],
    ) -> Tuple[float, str, float]:
        entries = [context.get(subject, {}), context.get(object_, {})]
        weight = 1.0
        labels: List[str] = []
        confidences: List[float] = []

        def _apply(entry: Mapping[str, object]) -> None:
            nonlocal weight, labels, confidences
            species = entry.get("species", set())
            if isinstance(species, set):
                species_lower = {str(item).lower() for item in species}
                if "homo sapiens" in species_lower:
                    weight += 0.12
                    labels.append("human data")
                elif species_lower:
                    weight += 0.05
                    labels.append("preclinical data")
            timecourse = entry.get("timecourse", set())
            if isinstance(timecourse, set):
                joined = ",".join(str(item).lower() for item in timecourse)
                if "chronic" in joined or "longitudinal" in joined:
                    weight += 0.08
                    labels.append("chronic evidence")
                elif "acute" in joined:
                    weight += 0.02
            regions = entry.get("regions", set())
            if isinstance(regions, set):
                limbic = {"nucleus accumbens", "vta", "ventral tegmental area", "mpfc", "amygdala"}
                region_lower = {str(item).lower() for item in regions}
                if limbic & region_lower:
                    weight += 0.05
                    labels.append("limbic circuitry")
            behaviors = entry.get("behaviors", set())
            if isinstance(behaviors, set) and behaviors:
                weight += 0.03
                labels.append("behavioural tagging")
            confidence = entry.get("confidence", [])
            if isinstance(confidence, list) and confidence:
                mean_conf = float(sum(confidence) / len(confidence))
                confidences.extend(float(value) for value in confidence)
                weight += 0.05 * (mean_conf - 0.5)

        for entry in entries:
            if entry:
                _apply(entry)

        weight = float(max(0.6, min(1.6, weight)))
        description = ", ".join(dict.fromkeys(labels)) if labels else ""
        if confidences:
            clipped = [float(max(0.0, min(1.0, value))) for value in confidences]
            mean_conf = float(sum(clipped) / len(clipped))
        else:
            mean_conf = 0.5
        uncertainty = float(max(0.0, min(1.0, 1.0 - mean_conf)))
        return weight, description, uncertainty

    @staticmethod
    def _normalize_to_set(value: object) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            cleaned = value.strip()
            return {cleaned} if cleaned else set()
        if isinstance(value, (list, tuple, set)):
            result: set[str] = set()
            for item in value:
                result.update(EmbeddingGapFinder._normalize_to_set(item))
            return result
        return {str(value)}


EmbeddingGapFinder = RotatEGapFinder


__all__ = [
    "EmbeddingConfig",
    "EmbeddingGapFinder",
    "GapCandidate",
    "GapReport",
    "RotatEGapFinder",
]

