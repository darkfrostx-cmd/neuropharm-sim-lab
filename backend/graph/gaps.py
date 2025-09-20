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
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

from .models import BiolinkPredicate, Edge, Node
from .persistence import GraphStore


@dataclass(slots=True)
class EmbeddingConfig:
    """Configuration for the lightweight embedding trainer."""

    embedding_dim: int = 16
    learning_rate: float = 0.02
    epochs: int = 150
    negative_ratio: int = 2
    regularization: float = 1e-3
    seed: int = 13


@dataclass(slots=True)
class GapCandidate:
    """Potential missing edge predicted by the embedding model."""

    subject: str
    object: str
    predicate: BiolinkPredicate
    score: float
    impact: float
    reason: str = "Embedding model highlighted this relation as a likely gap."
    metadata: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class GapReport:
    """Structured report shared with the API layer."""

    subject: str
    object: str
    predicate: BiolinkPredicate
    embedding_score: float
    impact_score: float
    reason: str
    causal_effect: float | None = None
    causal_direction: str | None = None
    causal_confidence: float | None = None
    counterfactual_summary: str | None = None
    literature: List[str] = field(default_factory=list)


class EmbeddingGapFinder:
    """Train and query a simple TransE-like embedding over the graph."""

    def __init__(self, store: GraphStore, config: EmbeddingConfig | None = None) -> None:
        self.store = store
        self.config = config or EmbeddingConfig()
        self._node_index: Dict[str, int] = {}
        self._relation_index: Dict[BiolinkPredicate, int] = {}
        self._entity_embeddings: np.ndarray | None = None
        self._relation_embeddings: np.ndarray | None = None
        self._snapshot: Tuple[int, int] | None = None

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
        candidates: List[GapCandidate] = []
        for subject in focus_nodes:
            if subject not in self._node_index:
                continue
            for node_id in nodes:
                if node_id == subject:
                    continue
                if (subject, node_id) not in existing_pairs:
                    best = self._best_predicate(subject, node_id)
                    if best is None:
                        continue
                    predicate, score = best
                    impact = self._impact_score(score, degrees.get(subject, 0), degrees.get(node_id, 0))
                    if node_id in focus_targets:
                        impact /= 1.5
                    candidates.append(
                        GapCandidate(
                            subject=subject,
                            object=node_id,
                            predicate=predicate,
                            score=score,
                            impact=impact,
                            metadata={"degree_sum": float(degrees.get(subject, 0) + degrees.get(node_id, 0))},
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
        self._entity_embeddings = rng.normal(scale=0.1, size=(len(self._node_index), self.config.embedding_dim)).astype(np.float32)
        self._relation_embeddings = rng.normal(scale=0.1, size=(len(self._relation_index), self.config.embedding_dim)).astype(np.float32)

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
        predicate_vec = self._relation_embeddings[predicate_idx]
        object_vec = self._entity_embeddings[object_idx]
        diff = subject_vec + predicate_vec - object_vec
        subject_vec -= lr * diff
        predicate_vec -= lr * diff
        object_vec += lr * diff
        self._entity_embeddings[subject_idx] = self._project(subject_vec, reg)
        self._relation_embeddings[predicate_idx] = self._project(predicate_vec, reg)
        self._entity_embeddings[object_idx] = self._project(object_vec, reg)

    def _apply_negative_update(self, subject_idx: int, predicate_idx: int, object_idx: int, lr: float, reg: float) -> None:
        assert self._entity_embeddings is not None and self._relation_embeddings is not None
        subject_vec = self._entity_embeddings[subject_idx]
        predicate_vec = self._relation_embeddings[predicate_idx]
        object_vec = self._entity_embeddings[object_idx]
        diff = subject_vec + predicate_vec - object_vec
        subject_vec += lr * diff
        predicate_vec += lr * diff
        object_vec -= lr * diff
        self._entity_embeddings[subject_idx] = self._project(subject_vec, reg)
        self._relation_embeddings[predicate_idx] = self._project(predicate_vec, reg)
        self._entity_embeddings[object_idx] = self._project(object_vec, reg)

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
        distance = np.linalg.norm(subject_vec + predicate_vec - object_vec)
        return float(-distance)

    def _impact_score(self, embedding_score: float, subject_degree: int, object_degree: int) -> float:
        degree_factor = math.log(2 + subject_degree + object_degree)
        return embedding_score * degree_factor

    @staticmethod
    def _compute_degrees(edges: Sequence[Edge]) -> Dict[str, int]:
        degrees: Dict[str, int] = {}
        for edge in edges:
            degrees[edge.subject] = degrees.get(edge.subject, 0) + 1
            degrees[edge.object] = degrees.get(edge.object, 0) + 1
        return degrees

    def _project(self, vector: np.ndarray, reg: float) -> np.ndarray:
        """Apply L2 regularisation and norm clipping to keep embeddings stable."""

        vector = vector * (1 - reg)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        max_norm = math.sqrt(self.config.embedding_dim)
        if norm > max_norm:
            vector = (vector / norm) * max_norm
        return vector


__all__ = [
    "EmbeddingConfig",
    "EmbeddingGapFinder",
    "GapCandidate",
    "GapReport",
]

