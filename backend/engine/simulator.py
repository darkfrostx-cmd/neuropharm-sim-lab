"""Simulation engine for the Neuropharm Simulation Lab API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from .receptors import (
    RECEPTORS,
    canonical_receptor_name,
    get_mechanism_factor,
    get_receptor_weights,
)


class SimulationError(Exception):
    """Raised when the simulation engine cannot evaluate a payload."""


@dataclass(slots=True)
class SimulationResult:
    """Container for simulation outputs returned by the engine."""

    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, list[Dict[str, str]]]


class SimulationEngine:
    """Encapsulates the scoring logic used by `/simulate` and related routes."""

    METRICS = (
        "drive",
        "apathy",
        "motivation",
        "cognitive_flexibility",
        "anxiety",
        "sleep_quality",
    )

    def __init__(self, receptor_refs: Mapping[str, list[dict[str, str]]] | None = None) -> None:
        self._receptor_refs = dict(receptor_refs or self._load_refs())

    @staticmethod
    def _load_refs() -> Mapping[str, list[dict[str, str]]]:
        refs_path = Path(__file__).resolve().parent.parent / "refs.json"
        if not refs_path.exists():
            return {}
        with refs_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, Mapping):  # pragma: no cover - defensive
            return {}
        return data  # type: ignore[return-value]

    def run(
        self,
        receptors: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        acute_1a: bool = False,
        adhd: bool = False,
        gut_bias: bool = False,
        pvt_weight: float = 0.5,
    ) -> SimulationResult:
        """Execute the simulation for a given receptor configuration."""

        receptors = receptors or {}
        contributions: Dict[str, float] = {metric: 0.0 for metric in self.METRICS}

        for receptor_name, spec in receptors.items():
            canon = canonical_receptor_name(receptor_name)
            if canon not in RECEPTORS:
                continue
            try:
                weights = get_receptor_weights(canon)
            except KeyError as exc:  # pragma: no cover - defensive
                raise SimulationError(f"Unknown receptor '{canon}'") from exc
            mechanism = spec.get("mech")
            occupancy = spec.get("occ", 0.0)
            try:
                factor = get_mechanism_factor(str(mechanism))
            except ValueError as exc:
                raise SimulationError(str(exc)) from exc
            for metric, weight in weights.items():
                contributions[metric] += weight * float(occupancy) * factor

        if adhd:
            contributions["drive"] -= 0.3
            contributions["motivation"] -= 0.2
        if gut_bias:
            for metric in contributions:
                if contributions[metric] < 0:
                    contributions[metric] *= 0.9
        if acute_1a:
            for metric in contributions:
                contributions[metric] *= 0.75

        scale = 1.0 - (float(pvt_weight) * 0.2)
        for metric in contributions:
            contributions[metric] *= scale

        scores: Dict[str, float] = {}
        for metric, value in contributions.items():
            baseline = 50.0
            change = 20.0 * value
            score = baseline + change
            if metric == "apathy":
                score = 100.0 - score
            name_map = {
                "drive": "DriveInvigoration",
                "apathy": "ApathyBlunting",
                "motivation": "Motivation",
                "cognitive_flexibility": "CognitiveFlexibility",
                "anxiety": "Anxiety",
                "sleep_quality": "SleepQuality",
            }
            scores[name_map[metric]] = max(0.0, min(100.0, score))

        citations: Dict[str, list[Dict[str, str]]] = {}
        for receptor_name in receptors:
            canon = canonical_receptor_name(receptor_name)
            refs = self._receptor_refs.get(canon)
            if refs:
                citations[canon] = [dict(ref) for ref in refs]

        details: Dict[str, Any] = {
            "raw_contributions": dict(contributions),
            "final_scores": dict(scores),
        }
        return SimulationResult(scores=scores, details=details, citations=citations)


__all__ = ["SimulationEngine", "SimulationError", "SimulationResult"]
