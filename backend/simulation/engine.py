"""High level simulation orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Mapping, MutableMapping, Literal

import numpy as np

from ..engine.receptors import canonical_receptor_name, get_mechanism_factor, get_receptor_weights
from .circuit import CircuitParameters, simulate_circuit_response
from .molecular import MolecularCascadeParams, simulate_cascade
from .pkpd import PKPDParameters, simulate_pkpd
from .assets import load_reference_pathway

Mechanism = Literal["agonist", "antagonist", "partial", "inverse"]


@dataclass(frozen=True)
class ReceptorEngagement:
    """Normalised receptor engagement derived from the knowledge graph."""

    name: str
    occupancy: float
    mechanism: Mechanism
    kg_weight: float
    evidence: float
    affinity: float | None = None
    expression: float | None = None
    evidence_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineRequest:
    """Input payload for the orchestration layer."""

    receptors: Mapping[str, ReceptorEngagement]
    regimen: Literal["acute", "chronic"]
    adhd: bool
    gut_bias: bool
    pvt_weight: float


@dataclass(frozen=True)
class EngineResult:
    """Structured result returned by :class:`SimulationEngine`."""

    scores: Dict[str, float]
    timepoints: list[float]
    trajectories: Dict[str, list[float]]
    module_summaries: Dict[str, Any]
    confidence: Dict[str, float]



REFERENCE_PATHWAY = load_reference_pathway()
REFERENCE_PATHWAY_NAME = REFERENCE_PATHWAY.get("pathway", "monoamine_neurotrophin_cascade")
REFERENCE_DOWNSTREAM_NODES = {str(key): float(value) for key, value in REFERENCE_PATHWAY.get("downstream_nodes", {}).items()}

class SimulationEngine:
    """Coordinate the molecular, PK/PD, and circuit layers."""

    def __init__(self, time_step: float = 1.0) -> None:
        self.time_step = time_step

    def run(self, request: EngineRequest) -> EngineResult:
        """Execute the multi-layer simulation."""

        horizon = 24.0 if request.regimen == "acute" else 24.0 * 7
        timepoints = np.arange(0.0, horizon + self.time_step, self.time_step)

        canonical_entries: Dict[str, ReceptorEngagement] = {}
        for provided_name, engagement in request.receptors.items():
            canonical_name = canonical_receptor_name(provided_name or engagement.name)
            normalised = replace(engagement, name=canonical_name)
            existing = canonical_entries.get(canonical_name)
            if existing is None:
                canonical_entries[canonical_name] = normalised
            else:
                canonical_entries[canonical_name] = self._merge_engagements(existing, normalised)
        receptor_states: Dict[str, float] = {
            name: engagement.occupancy for name, engagement in canonical_entries.items()
        }
        def _affinity_factor(value: float | None) -> float:
            if value is None:
                return 1.0
            return float(max(0.5, min(1.4, 0.6 + 0.4 * value)))

        def _expression_factor(value: float | None) -> float:
            if value is None:
                return 1.0
            return float(max(0.6, min(1.35, 0.7 + 0.3 * value)))

        receptor_weights: Dict[str, float] = {}
        receptor_evidence: Dict[str, float] = {}
        behaviour_axes: Dict[str, float] = {}
        for name, engagement in canonical_entries.items():
            weight = engagement.kg_weight
            weight *= _affinity_factor(engagement.affinity)
            weight *= _expression_factor(engagement.expression)
            receptor_weights[name] = float(max(0.05, min(1.2, weight)))

            evidence_value = engagement.evidence
            if engagement.evidence_sources:
                evidence_value = min(0.99, evidence_value + 0.02 * len(engagement.evidence_sources))
            receptor_evidence[name] = float(max(0.05, min(0.99, evidence_value)))
            try:
                receptor_weights_profile = get_receptor_weights(name)
                mechanism_factor = get_mechanism_factor(engagement.mechanism)
            except KeyError:
                continue
            scale = engagement.occupancy * receptor_weights[name] * mechanism_factor * (
                0.5 + 0.5 * receptor_evidence[name]
            )
            for axis, axis_weight in receptor_weights_profile.items():
                behaviour_axes[axis] = behaviour_axes.get(axis, 0.0) + scale * axis_weight
        mean_evidence = float(np.mean(list(receptor_evidence.values()) or [0.5]))

        molecular_params = MolecularCascadeParams(
            pathway=REFERENCE_PATHWAY_NAME,
            receptor_states=receptor_states,
            receptor_weights=receptor_weights,
            receptor_evidence=receptor_evidence,
            downstream_nodes=(REFERENCE_DOWNSTREAM_NODES or {"CREB": 0.18, "BDNF": 0.09, "mTOR": 0.05}),
            stimulus=1.2 if request.regimen == "chronic" else 1.0,
            timepoints=timepoints,
        )
        molecular_result = simulate_cascade(molecular_params)

        avg_occ = float(np.mean(list(receptor_states.values()) or [0.0]))
        dose_mg = 50.0 * max(0.25, avg_occ)
        clearance_rate = 0.15 if request.regimen == "acute" else 0.08
        pkpd_params = PKPDParameters(
            compound="composite_ssri",
            dose_mg=dose_mg,
            dosing_interval_h=24.0,
            regimen=request.regimen,
            clearance_rate=clearance_rate,
            bioavailability=0.55 + 0.35 * avg_occ,
            brain_plasma_ratio=0.75 + 0.1 * avg_occ,
            receptor_occupancy=receptor_states,
            kg_confidence=mean_evidence,
            simulation_hours=horizon,
            time_step=self.time_step,
        )
        pkpd_profile = simulate_pkpd(pkpd_params)

        serotonin_drive = float(np.tanh(molecular_result.summary["steady_state"]))
        dopamine_drive = float(
            np.tanh(molecular_result.summary["transient_peak"] * (1.0 - request.pvt_weight * 0.3))
        )
        noradrenaline_drive = float(np.tanh(molecular_result.summary["activation_index"] * 0.5))

        if request.adhd:
            dopamine_drive *= 0.85
            noradrenaline_drive *= 0.9
        if request.gut_bias:
            serotonin_drive *= 1.05

        auc_scaled = float(np.tanh(pkpd_profile.summary["auc"] / 100.0))
        connectivity: MutableMapping[tuple[str, str], float] = {}
        regions = ("prefrontal", "striatum", "amygdala")
        for src in regions:
            for dst in regions:
                if src == dst:
                    continue
                connectivity[(src, dst)] = 0.2 + 0.3 * auc_scaled

        circuit_params = CircuitParameters(
            regions=regions,
            connectivity=connectivity,
            neuromodulator_drive={
                "serotonin": serotonin_drive,
                "dopamine": dopamine_drive,
                "noradrenaline": noradrenaline_drive,
            },
            regimen=request.regimen,
            timepoints=timepoints,
            coupling_baseline=0.25 + 0.4 * auc_scaled,
            kg_confidence=mean_evidence,
        )
        circuit_response = simulate_circuit_response(circuit_params)

        def _score_from_index(index: float, invert: bool = False) -> float:
            centred = 50.0 + 100.0 * (index - 0.5)
            if invert:
                centred = 100.0 - centred
            return float(max(0.0, min(100.0, centred)))

        scores: Dict[str, float] = {
            "DriveInvigoration": _score_from_index(circuit_response.global_metrics["drive_index"]),
            "ApathyBlunting": _score_from_index(circuit_response.global_metrics["apathy_index"], invert=True),
            "Motivation": _score_from_index(
                0.5 * circuit_response.global_metrics["drive_index"]
                + 0.5 * np.clip(molecular_result.summary["activation_index"], 0.0, 1.0)
            ),
            "CognitiveFlexibility": _score_from_index(circuit_response.global_metrics["flexibility_index"]),
            "Anxiety": _score_from_index(circuit_response.global_metrics["anxiety_index"], invert=True),
            "SleepQuality": _score_from_index(1.0 - pkpd_profile.uncertainty["exposure"]),
        }

        def _behaviour_metric(value: float, invert: bool = False) -> float:
            scaled = float(np.tanh(value))
            score = 50.0 + 45.0 * scaled
            if invert:
                score = 100.0 - score
            return float(max(0.0, min(100.0, score)))

        if behaviour_axes:
            scores["SocialAffiliation"] = _behaviour_metric(behaviour_axes.get("social_affiliation", 0.0))
            scores["ExplorationBias"] = _behaviour_metric(behaviour_axes.get("exploration", 0.0))
            scores["SalienceProcessing"] = _behaviour_metric(
                behaviour_axes.get("salience", 0.0)
                + circuit_response.global_metrics["flexibility_index"] * 0.25
            )

        if request.adhd:
            scores["Motivation"] = max(0.0, scores["Motivation"] - 5.0)
            scores["CognitiveFlexibility"] = max(0.0, scores["CognitiveFlexibility"] - 4.0)
        if request.gut_bias:
            scores["SleepQuality"] = min(100.0, scores["SleepQuality"] + 3.0)
            scores["Anxiety"] = min(100.0, scores["Anxiety"] + 4.0)

        module_uncertainties = {
            "molecular": molecular_result.uncertainty["cascade"],
            "pkpd": pkpd_profile.uncertainty["pkpd"],
            "circuit": circuit_response.uncertainty["network"],
        }
        base_conf = float(max(0.05, 1.0 - np.mean(list(module_uncertainties.values()))))
        confidence = {
            metric: float(
                max(
                    0.05,
                    min(
                        0.99,
                        base_conf
                        * (1.0 - 0.3 * module_uncertainties["molecular"])
                        * (1.0 - 0.3 * module_uncertainties["pkpd"])
                        * (1.0 - 0.4 * module_uncertainties["circuit"]),
                    ),
                )
            )
            for metric in scores.keys()
        }

        trajectories = {
            "plasma_concentration": pkpd_profile.plasma_concentration.astype(float).tolist(),
            "brain_concentration": pkpd_profile.brain_concentration.astype(float).tolist(),
        }
        occupancy_profiles = pkpd_profile.summary.get("occupancy_profile")
        if isinstance(occupancy_profiles, dict):
            for receptor, series in occupancy_profiles.items():
                trajectories[f"occupancy_{receptor.lower()}"] = list(series)
        for node, values in molecular_result.node_activity.items():
            trajectories[f"cascade_{node.lower()}"] = values.astype(float).tolist()
        for region, values in circuit_response.region_activity.items():
            trajectories[f"region_{region.lower()}"] = values.astype(float).tolist()

        module_summaries: Dict[str, Any] = {
            "molecular": molecular_result.summary,
            "pkpd": pkpd_profile.summary,
            "circuit": circuit_response.global_metrics,
            "receptor_inputs": {
                name: {
                    "occupancy": engagement.occupancy,
                    "mechanism": engagement.mechanism,
                    "kg_weight": receptor_weights[name],
                    "affinity": engagement.affinity,
                    "expression": engagement.expression,
                    "evidence": receptor_evidence[name],
                    "sources": list(engagement.evidence_sources),
                }
                for name, engagement in canonical_entries.items()
            },
        }
        if behaviour_axes:
            module_summaries["behavioural_axes"] = behaviour_axes

        return EngineResult(
            scores=scores,
            timepoints=timepoints.astype(float).tolist(),
            trajectories=trajectories,
            module_summaries=module_summaries,
            confidence=confidence,
        )

    @staticmethod
    def _merge_engagements(primary: ReceptorEngagement, secondary: ReceptorEngagement) -> ReceptorEngagement:
        """Combine two engagements that map to the same canonical receptor."""

        dominant = primary if primary.evidence >= secondary.evidence else secondary
        weight_primary = max(primary.evidence, 1e-3)
        weight_secondary = max(secondary.evidence, 1e-3)
        total_weight = weight_primary + weight_secondary
        occupancy = (
            primary.occupancy * weight_primary + secondary.occupancy * weight_secondary
        ) / total_weight
        kg_weight = (
            primary.kg_weight * weight_primary + secondary.kg_weight * weight_secondary
        ) / total_weight
        evidence = float(max(primary.evidence, secondary.evidence))

        affinities = [value for value in (primary.affinity, secondary.affinity) if value is not None]
        affinity = float(sum(affinities) / len(affinities)) if affinities else None
        expressions = [value for value in (primary.expression, secondary.expression) if value is not None]
        expression = float(sum(expressions) / len(expressions)) if expressions else None
        sources = tuple(sorted(set(primary.evidence_sources) | set(secondary.evidence_sources)))

        return ReceptorEngagement(
            name=dominant.name,
            occupancy=float(max(0.0, min(1.0, occupancy))),
            mechanism=dominant.mechanism,
            kg_weight=float(max(0.0, min(1.2, kg_weight))),
            evidence=float(max(0.0, min(0.99, evidence))),
            affinity=affinity,
            expression=expression,
            evidence_sources=sources,
        )
