"""Adapters that translate knowledge graph evidence into engine inputs."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Dict, Iterable, List, Sequence, Set

from ..engine.receptors import canonical_receptor_name
from ..graph.evidence_quality import EdgeQualitySummary, EvidenceQualityScorer
from ..graph.models import BiolinkPredicate, Edge, Node
from ..graph.service import GraphService


@dataclass(frozen=True)
class ReceptorEvidenceBundle:
    """Container describing evidence-derived receptor parameters."""

    kg_weight: float
    evidence_score: float
    affinity: float | None
    expression: float | None
    evidence_sources: tuple[str, ...]
    evidence_count: int


class GraphBackedReceptorAdapter:
    """Aggregate receptor context from the knowledge graph."""

    def __init__(
        self,
        graph_service: GraphService,
        default_kg_weight: float = 0.25,
        default_evidence: float = 0.45,
        quality_scorer: EvidenceQualityScorer | None = None,
    ) -> None:
        self.graph_service = graph_service
        self.default_kg_weight = default_kg_weight
        self.default_evidence = default_evidence
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._identifier_cache: Dict[str, Sequence[str]] = {}
        self.quality_scorer = quality_scorer or EvidenceQualityScorer()

    # ------------------------------------------------------------------
    # Cache management helpers
    # ------------------------------------------------------------------
    def clear_cache(self) -> None:
        """Remove all cached receptor lookups."""

        self._cache.clear()
        self._identifier_cache.clear()

    def invalidate(self, receptor: str) -> None:
        """Invalidate cached evidence for a specific receptor."""

        canon = canonical_receptor_name(receptor)
        self._cache.pop(canon, None)
        self._identifier_cache.pop(canon, None)

    def identifiers_for(self, receptor: str) -> Sequence[str]:
        """Return identifier candidates understood by the knowledge graph."""

        canon = canonical_receptor_name(receptor)
        cached = self._identifier_cache.get(canon)
        if cached is None:
            cached = tuple(self._candidate_identifiers(canon))
            self._identifier_cache[canon] = cached
        return list(cached)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def derive(
        self,
        receptor: str,
        *,
        fallback_weight: float | None = None,
        fallback_evidence: float | None = None,
    ) -> ReceptorEvidenceBundle:
        """Return a :class:`ReceptorEvidenceBundle` for ``receptor``.

        Parameters
        ----------
        receptor:
            Name of the receptor using any identifier understood by
            :func:`canonical_receptor_name`.
        fallback_weight:
            Baseline weight used if the knowledge graph lacks interaction
            data.
        fallback_evidence:
            Baseline evidence score when no citations or confidences are
            available.
        """

        canon = canonical_receptor_name(receptor)
        raw = self._cache.get(canon)
        if raw is None:
            raw = self._compute_raw_metrics(canon)
            self._cache[canon] = raw
        return self._build_bundle(raw, fallback_weight, fallback_evidence)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_bundle(
        self,
        raw: Dict[str, Any],
        fallback_weight: float | None,
        fallback_evidence: float | None,
    ) -> ReceptorEvidenceBundle:
        kg_weight = raw["kg_weight"]
        evidence_score = raw["evidence"]

        baseline_weight = fallback_weight if fallback_weight is not None else self.default_kg_weight
        baseline_evidence = fallback_evidence if fallback_evidence is not None else self.default_evidence

        if kg_weight is None:
            kg_weight = baseline_weight
        if evidence_score is None:
            evidence_score = baseline_evidence

        kg_weight = float(max(0.05, min(0.95, kg_weight)))
        evidence_score = float(max(0.05, min(0.99, evidence_score)))

        return ReceptorEvidenceBundle(
            kg_weight=kg_weight,
            evidence_score=evidence_score,
            affinity=raw.get("affinity"),
            expression=raw.get("expression"),
            evidence_sources=tuple(raw.get("sources", ())),
            evidence_count=int(raw.get("evidence_count", 0)),
        )

    def _compute_raw_metrics(self, canon: str) -> Dict[str, Any]:
        identifiers = self.identifiers_for(canon)
        edges = self._collect_edges(identifiers)

        affinity_values: List[float] = []
        expression_values: List[float] = []
        evidence_values: List[float] = []
        sources: set[str] = set()

        has_interaction = False
        has_expression = False

        for edge in edges:
            predicate = edge.predicate
            if predicate == BiolinkPredicate.INTERACTS_WITH:
                has_interaction = True
            if predicate in {BiolinkPredicate.EXPRESSES, BiolinkPredicate.COEXPRESSION_WITH}:
                has_expression = True

            quality = self.quality_scorer.summarise_edge(edge)

            self._harvest_from_edge(
                edge,
                quality_summary=quality,
                affinity_values=affinity_values,
                expression_values=expression_values,
                evidence_values=evidence_values,
                sources=sources,
            )

        affinity = _combine_scores(affinity_values, default=None, scale=6.0)
        expression = _combine_scores(expression_values, default=None, scale=8.0)
        evidence_norm = _combine_scores(evidence_values, default=None, scale=5.0)

        if affinity is None and has_interaction:
            affinity = 0.45
        if expression is None and has_expression:
            expression = 0.4
        if evidence_norm is None and edges:
            evidence_norm = 0.5

        kg_weight = _combine_kg_weight(affinity, expression, evidence_norm)
        evidence_score = None
        if evidence_norm is not None:
            coverage_bonus = min(0.25, 0.07 * len(sources))
            evidence_score = float(0.35 + 0.5 * evidence_norm + coverage_bonus)

        return {
            "affinity": affinity,
            "expression": expression,
            "evidence": evidence_score,
            "kg_weight": kg_weight,
            "sources": tuple(sorted(sources)),
            "evidence_count": len(evidence_values),
        }

    def _candidate_identifiers(self, canon: str) -> Sequence[str]:
        base = canon.strip()
        seeds: List[str] = []
        if base:
            seeds.extend([base, base.replace("-", ""), base.upper()])
        compact = base.replace("-", "").upper()
        if compact.startswith("5HT"):
            suffix = compact[3:]
            gene = f"HTR{suffix}"
            seeds.extend([gene, f"HGNC:{gene}"])
        aliases = self._discover_graph_aliases(seeds)
        seeds.extend(sorted(aliases))
        filtered = [candidate for candidate in seeds if candidate]
        return list(dict.fromkeys(filtered))

    def _discover_graph_aliases(self, seeds: Sequence[str]) -> Set[str]:
        store = getattr(self.graph_service, "store", None)
        if store is None:
            return set()

        def _tokenise(value: str) -> str:
            cleaned = re.sub(r"[^A-Za-z0-9]+", "", value.upper())
            return cleaned

        aliases: Set[str] = set()
        tokens = {_tokenise(seed) for seed in seeds if seed}
        tokens.discard("")

        if not tokens:
            return aliases

        examined: Set[str] = set()
        for seed in seeds:
            if not seed:
                continue
            try:
                node = store.get_node(seed)
            except NotImplementedError:  # pragma: no cover - backend without lookup support
                node = None
            if node is None:
                continue
            examined.add(node.id)
            aliases.update(self._aliases_from_node(node))
            tokens.add(_tokenise(node.id))

        try:
            iterable: Iterable[Node] = store.all_nodes()
        except NotImplementedError:  # pragma: no cover - backend without iteration support
            iterable = ()

        for node in iterable:
            if node.id in examined:
                continue
            node_aliases = self._aliases_from_node(node)
            node_tokens = {_tokenise(alias) for alias in node_aliases}
            node_tokens.add(_tokenise(node.id))
            if node_tokens & tokens:
                aliases.update(node_aliases)
                aliases.add(node.id)

        return {alias for alias in aliases if alias}

    @staticmethod
    def _aliases_from_node(node: Node) -> Set[str]:
        aliases: Set[str] = {node.id, node.name}
        aliases.update(node.synonyms)
        aliases.update(node.xrefs)

        for key in ("hgnc", "hgnc_id", "ensembl", "ensembl_gene", "ncbi", "ncbi_gene", "symbol", "gene_symbol"):
            value = node.attributes.get(key)
            if isinstance(value, str):
                aliases.add(value)
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        aliases.add(item)
                    elif item is not None:
                        aliases.add(str(item))

        return {alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip()}

    def _collect_edges(self, identifiers: Sequence[str]) -> List[Edge]:
        seen: Dict[tuple[str, str, str], Edge] = {}
        for identifier in identifiers:
            for summary in self.graph_service.get_evidence(subject=identifier):
                seen[summary.edge.key] = summary.edge
            for summary in self.graph_service.get_evidence(object_=identifier):
                seen[summary.edge.key] = summary.edge
        return list(seen.values())

    def _harvest_from_edge(
        self,
        edge: Edge,
        *,
        quality_summary: EdgeQualitySummary,
        affinity_values: List[float],
        expression_values: List[float],
        evidence_values: List[float],
        sources: set[str],
    ) -> None:
        predicate = edge.predicate
        quality_score = quality_summary.score
        classifier_boost = quality_summary.classifier_probability
        quality_multiplier = 1.0
        if classifier_boost is not None:
            quality_multiplier = float(max(0.3, min(1.2, 0.6 + 0.6 * classifier_boost)))
        for breakdown in quality_summary.breakdowns:
            score = breakdown.total_score * quality_multiplier
            evidence_values.append(float(score))
            if predicate == BiolinkPredicate.INTERACTS_WITH:
                affinity_values.append(float(score))
            elif predicate in {BiolinkPredicate.EXPRESSES, BiolinkPredicate.COEXPRESSION_WITH}:
                expression_values.append(float(score))

        for key in ("affinity", "affinity_nM", "pchembl_value", "weight"):
            value = _safe_float(edge.qualifiers.get(key))
            if value is not None:
                weighted_value = value
                if quality_score is not None:
                    weighted_value = value * float(max(0.1, min(1.0, quality_score)))
                weighted_value *= quality_multiplier
                if predicate == BiolinkPredicate.INTERACTS_WITH:
                    affinity_values.append(weighted_value)
                elif predicate in {BiolinkPredicate.EXPRESSES, BiolinkPredicate.COEXPRESSION_WITH}:
                    expression_values.append(weighted_value)
                else:
                    evidence_values.append(weighted_value)

        if predicate in {BiolinkPredicate.EXPRESSES, BiolinkPredicate.COEXPRESSION_WITH}:
            for key in ("expression", "zscore", "tau"):
                value = _safe_float(edge.qualifiers.get(key))
                if value is not None:
                    weighted_value = value
                    if quality_score is not None:
                        weighted_value = value * float(max(0.1, min(1.0, quality_score)))
                    weighted_value *= quality_multiplier
                    expression_values.append(weighted_value)

        for ev in edge.evidence:
            if ev.source:
                sources.add(ev.source)
            # quality_summary already accounts for evidence confidences


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalise(value: float, *, scale: float) -> float:
    if value < 0:
        return 0.0
    if value > 1.0:
        return float(1.0 - math.exp(-value / max(scale, 1.0)))
    return float(max(0.0, min(1.0, value)))


def _combine_scores(values: Sequence[float], default: float | None, *, scale: float) -> float | None:
    cleaned: List[float] = []
    for raw in values:
        value = _safe_float(raw)
        if value is None:
            continue
        cleaned.append(_normalise(value, scale=scale))
    if cleaned:
        return float(sum(cleaned) / len(cleaned))
    return default


def _combine_kg_weight(
    affinity: float | None,
    expression: float | None,
    evidence: float | None,
) -> float | None:
    components: List[tuple[float, float]] = []
    if affinity is not None:
        components.append((affinity, 0.5))
    if expression is not None:
        components.append((expression, 0.3))
    if evidence is not None:
        components.append((evidence, 0.2))
    if not components:
        return None
    total_weight = sum(weight for _, weight in components)
    if total_weight <= 0:
        return None
    score = sum(value * weight for value, weight in components) / total_weight
    return float(max(0.05, min(0.95, score)))


__all__ = ["GraphBackedReceptorAdapter", "ReceptorEvidenceBundle"]
