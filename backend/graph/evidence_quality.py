"""Evidence quality scoring utilities.

These helpers normalise study metadata (species, chronicity, design)
into weights that can be combined with provenance and baseline
confidence values.  The resulting scores are used by both the API layer
and the simulation adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean
from typing import Dict, Iterable, Mapping, MutableMapping, Sequence

from .models import Edge, Evidence
from .evidence_classifier import EvidenceQualityClassifier

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


_SPECIES_ALIASES: Mapping[str, str] = {
    "human": "human",
    "homo sapiens": "human",
    "patient": "human",
    "mouse": "mouse",
    "mus musculus": "mouse",
    "rat": "rat",
    "rattus norvegicus": "rat",
    "macaque": "non_human_primate",
    "cynomolgus": "non_human_primate",
    "macaca mulatta": "non_human_primate",
    "dog": "canine",
    "canis lupus familiaris": "canine",
    "in vitro": "cell",
    "cell": "cell",
    "cell line": "cell",
}


_CHRONICITY_ALIASES: Mapping[str, str] = {
    "chronic": "chronic",
    "long term": "chronic",
    "subchronic": "subchronic",
    "acute": "acute",
    "single dose": "acute",
    "baseline": "acute",
}


_DESIGN_ALIASES: Mapping[str, str] = {
    "clinical": "clinical",
    "trial": "clinical",
    "observational": "clinical",
    "case": "clinical",
    "in vivo": "in_vivo",
    "invivo": "in_vivo",
    "in-vivo": "in_vivo",
    "ex vivo": "ex_vivo",
    "ex-vivo": "ex_vivo",
    "in vitro": "in_vitro",
    "in-vitro": "in_vitro",
    "binding": "in_vitro",
    "biochemical": "in_vitro",
    "computational": "in_silico",
    "model": "in_silico",
    "simulation": "in_silico",
    "literature": "meta_analysis",
    "meta": "meta_analysis",
}


_SPECIES_WEIGHTS: Mapping[str, float] = {
    "human": 0.95,
    "non_human_primate": 0.85,
    "canine": 0.75,
    "mouse": 0.7,
    "rat": 0.68,
    "cell": 0.6,
}

_CHRONICITY_WEIGHTS: Mapping[str, float] = {
    "chronic": 0.9,
    "subchronic": 0.78,
    "acute": 0.62,
}

_DESIGN_WEIGHTS: Mapping[str, float] = {
    "clinical": 0.95,
    "meta_analysis": 0.9,
    "in_vivo": 0.82,
    "ex_vivo": 0.75,
    "in_vitro": 0.68,
    "in_silico": 0.55,
}


def normalise_species_label(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if not lowered:
        return None
    for key, alias in _SPECIES_ALIASES.items():
        if key in lowered:
            return alias
    return lowered


def normalise_chronicity_label(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if not lowered:
        return None
    for key, alias in _CHRONICITY_ALIASES.items():
        if key in lowered:
            return alias
    return lowered


def normalise_design_label(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if not lowered:
        return None
    for key, alias in _DESIGN_ALIASES.items():
        if key in lowered:
            return alias
    return lowered


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceQualityBreakdown:
    """Detailed scoring for a single evidence record."""

    base_confidence: float
    provenance_score: float
    species: str | None
    species_score: float
    chronicity: str | None
    chronicity_score: float
    design: str | None
    design_score: float
    total_score: float


@dataclass(frozen=True)
class EdgeQualitySummary:
    """Aggregate quality assessment for an edge."""

    score: float | None
    breakdowns: tuple[EvidenceQualityBreakdown, ...]
    species_distribution: Mapping[str, int]
    chronicity_distribution: Mapping[str, int]
    design_distribution: Mapping[str, int]
    has_human_data: bool
    has_animal_data: bool
    classifier_label: str | None = None
    classifier_probability: float | None = None
    classifier_features: Mapping[str, float] = field(default_factory=dict)


class EvidenceQualityScorer:
    """Convert evidence metadata into weighted confidence metrics."""

    def __init__(
        self,
        default_confidence: float = 0.55,
        *,
        classifier: EvidenceQualityClassifier | None = None,
    ) -> None:
        self.default_confidence = max(0.05, min(0.95, float(default_confidence)))
        self._classifier = classifier

    def attach_classifier(self, classifier: EvidenceQualityClassifier | None) -> None:
        """Inject a trained classifier used during summarisation."""

        self._classifier = classifier

    # Public API -----------------------------------------------------------
    def score_evidence(self, evidence: Evidence) -> EvidenceQualityBreakdown:
        base_conf = self._clip(evidence.confidence, default=self.default_confidence)
        provenance_score = self._score_provenance(evidence)

        annotations: MutableMapping[str, object] = getattr(evidence, "annotations", {})
        species_raw = self._get_annotation(annotations, ["species", "organism", "study_species"])  # type: ignore[arg-type]
        species = normalise_species_label(species_raw)
        chronicity_raw = self._get_annotation(annotations, ["chronicity", "regimen", "timecourse"])  # type: ignore[arg-type]
        chronicity = normalise_chronicity_label(chronicity_raw)
        design_raw = self._get_annotation(annotations, ["design", "study_design", "assay", "assay_type"])  # type: ignore[arg-type]
        design = normalise_design_label(design_raw)

        species_score = _SPECIES_WEIGHTS.get(species or "", 0.55)
        chronicity_score = _CHRONICITY_WEIGHTS.get(chronicity or "", 0.55)
        design_score = _DESIGN_WEIGHTS.get(design or "", 0.6 if species == "human" else 0.55)

        total = (
            base_conf * 0.4
            + species_score * 0.25
            + chronicity_score * 0.15
            + design_score * 0.15
            + provenance_score * 0.05
        )
        total_score = float(max(0.05, min(0.99, total)))

        return EvidenceQualityBreakdown(
            base_confidence=base_conf,
            provenance_score=provenance_score,
            species=species,
            species_score=float(max(0.0, min(1.0, species_score))),
            chronicity=chronicity,
            chronicity_score=float(max(0.0, min(1.0, chronicity_score))),
            design=design,
            design_score=float(max(0.0, min(1.0, design_score))),
            total_score=total_score,
        )

    def summarise_edge(self, edge: Edge) -> EdgeQualitySummary:
        breakdowns = [self.score_evidence(evidence) for evidence in edge.evidence]
        if edge.confidence is not None:
            breakdowns.append(self._from_edge_confidence(edge))

        if breakdowns:
            score = fmean(breakdown.total_score for breakdown in breakdowns)
        else:
            score = None

        species_distribution = self._build_distribution(
            breakdowns, key=lambda bd: bd.species or "unspecified"
        )
        chronicity_distribution = self._build_distribution(
            breakdowns, key=lambda bd: bd.chronicity or "unspecified"
        )
        design_distribution = self._build_distribution(
            breakdowns, key=lambda bd: bd.design or "unspecified"
        )

        has_human = any(bd.species == "human" for bd in breakdowns)
        has_animal = any((bd.species or "") not in {"", "human", "cell"} for bd in breakdowns)

        classifier_label: str | None = None
        classifier_probability: float | None = None
        classifier_features: Dict[str, float] = {}
        if self._classifier is not None and breakdowns:
            classifier_features = self._features_from_breakdowns(breakdowns)
            try:
                classifier_label, classifier_probability = self._classifier.predict_label(classifier_features)
            except Exception:
                classifier_label = None
                classifier_probability = None
                classifier_features = {}

        return EdgeQualitySummary(
            score=float(score) if score is not None else None,
            breakdowns=tuple(breakdowns),
            species_distribution=species_distribution,
            chronicity_distribution=chronicity_distribution,
            design_distribution=design_distribution,
            has_human_data=has_human,
            has_animal_data=has_animal,
            classifier_label=classifier_label,
            classifier_probability=classifier_probability,
            classifier_features=classifier_features,
        )

    # Internal helpers ----------------------------------------------------
    @staticmethod
    def _get_annotation(annotations: Mapping[str, object], keys: Iterable[str]) -> str | None:
        for key in keys:
            value = annotations.get(key)
            if isinstance(value, str):
                if value.strip():
                    return value
            elif value is not None:
                return str(value)
        return None

    @staticmethod
    def _clip(value: float | None, *, default: float) -> float:
        if value is None:
            return default
        return float(max(0.05, min(0.99, value)))

    def _score_provenance(self, evidence: Evidence) -> float:
        reference = (evidence.reference or "").strip()
        if not reference:
            return 0.6
        if reference.lower().startswith("doi:"):
            return 0.92
        if reference.lower().startswith("pmid:") or reference.isdigit():
            return 0.88
        return 0.8

    def _from_edge_confidence(self, edge: Edge) -> EvidenceQualityBreakdown:
        base_conf = self._clip(edge.confidence, default=self.default_confidence)
        provenance_score = 0.88 if edge.publications else 0.65
        total = base_conf * 0.7 + provenance_score * 0.3
        total_score = float(max(0.05, min(0.99, total)))
        return EvidenceQualityBreakdown(
            base_confidence=base_conf,
            provenance_score=provenance_score,
            species=None,
            species_score=0.55,
            chronicity=None,
            chronicity_score=0.55,
            design=None,
            design_score=0.6,
            total_score=total_score,
        )

    @staticmethod
    def _build_distribution(
        breakdowns: Iterable[EvidenceQualityBreakdown], *, key
    ) -> Mapping[str, int]:  # type: ignore[override]
        counts: dict[str, int] = {}
        for breakdown in breakdowns:
            label = key(breakdown)
            counts[label] = counts.get(label, 0) + 1
        return counts

    def _features_from_breakdowns(
        self, breakdowns: Sequence[EvidenceQualityBreakdown]
    ) -> Dict[str, float]:
        totals = [bd.total_score for bd in breakdowns]
        species_scores = [bd.species_score for bd in breakdowns]
        chronicity_scores = [bd.chronicity_score for bd in breakdowns]
        design_scores = [bd.design_score for bd in breakdowns]
        features: Dict[str, float] = {
            "count": float(len(breakdowns)),
            "mean_total": float(fmean(totals)),
            "max_total": float(max(totals)),
            "min_total": float(min(totals)),
            "mean_species": float(fmean(species_scores)),
            "mean_chronicity": float(fmean(chronicity_scores)),
            "mean_design": float(fmean(design_scores)),
            "human_ratio": float(
                sum(1 for bd in breakdowns if bd.species == "human") / len(breakdowns)
            ),
            "clinical_ratio": float(
                sum(1 for bd in breakdowns if bd.design == "clinical") / len(breakdowns)
            ),
        }
        features["human_ratio"] = float(max(0.0, min(1.0, features["human_ratio"])))
        features["clinical_ratio"] = float(max(0.0, min(1.0, features["clinical_ratio"])))
        return features


__all__ = [
    "EvidenceQualityBreakdown",
    "EdgeQualitySummary",
    "EvidenceQualityScorer",
    "normalise_species_label",
    "normalise_chronicity_label",
    "normalise_design_label",
]
