"""High level simulation orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, MutableMapping, Literal

import numpy as np

from ..engine.receptors import canonical_receptor_name, get_mechanism_factor, get_receptor_weights
from .circuit import CircuitParameters, simulate_circuit_response
from .molecular import MolecularCascadeParams, simulate_cascade
from .pkpd import PKPDParameters, simulate_pkpd
from .assets import load_reference_connectivity, load_reference_pathway

Mechanism = Literal["agonist", "antagonist", "partial", "inverse"]


BEHAVIORAL_TAG_MAP: Dict[str, Dict[str, Any]] = {
    "DriveInvigoration": {
        "label": "Approach motivation",
        "rdoc": {"id": "RDoC:POS_APPR", "label": "Positive Valence – Approach Motivation"},
        "cogatlas": {"id": "trm_4a3fd79d0b4b8", "label": "approach motivation"},
        "domain": "Positive Valence Systems",
    },
    "ApathyBlunting": {
        "label": "Apathy / negative symptoms",
        "rdoc": {"id": "RDoC:NEG_LACK_APPETITIVE", "label": "Negative Valence – Loss"},
        "cogatlas": {"id": "trm_566748f4d3b95", "label": "apathy"},
        "domain": "Negative Valence Systems",
    },
    "Motivation": {
        "label": "Reward responsiveness",
        "rdoc": {"id": "RDoC:POS_INITIAL_RESP", "label": "Positive Valence – Initial responsiveness"},
        "cogatlas": {"id": "trm_4a3fd79d0a6da", "label": "motivation"},
        "domain": "Positive Valence Systems",
    },
    "CognitiveFlexibility": {
        "label": "Cognitive control",
        "rdoc": {"id": "RDoC:COG_COG_CONTROL", "label": "Cognitive Systems – Cognitive Control"},
        "cogatlas": {"id": "trm_4a3fd79d0b2c5", "label": "cognitive control"},
        "domain": "Cognitive Systems",
    },
    "Anxiety": {
        "label": "Anxious arousal",
        "rdoc": {"id": "RDoC:NEG_POT_THREAT", "label": "Negative Valence – Potential Threat"},
        "cogatlas": {"id": "trm_4a3fd79d0a239", "label": "anxiety"},
        "domain": "Negative Valence Systems",
    },
    "SleepQuality": {
        "label": "Circadian rhythm stability",
        "rdoc": {"id": "RDoC:AROUSAL_CIRCADIAN", "label": "Arousal/Regulatory Systems – Circadian Rhythms"},
        "cogatlas": {"id": "trm_4a3fd79d09ab1", "label": "sleep quality"},
        "domain": "Arousal/Regulatory Systems",
    },
    "SocialAffiliation": {
        "label": "Affiliation and attachment",
        "rdoc": {"id": "RDoC:SP_AFFILIATION", "label": "Social Processes – Affiliation and Attachment"},
        "cogatlas": {"id": "trm_4a3fd79d0b310", "label": "social affiliation"},
        "domain": "Social Processes",
    },
    "ExplorationBias": {
        "label": "Exploratory behaviour",
        "rdoc": {"id": "RDoC:POS_EXPLORATION", "label": "Positive Valence – Probabilistic/Exploratory behaviour"},
        "cogatlas": {"id": "tsk_4a57abb9490f5", "label": "exploration"},
        "domain": "Positive Valence Systems",
    },
    "SalienceProcessing": {
        "label": "Salience attribution",
        "rdoc": {"id": "RDoC:COG_PERCEPTION", "label": "Cognitive Systems – Perception"},
        "cogatlas": {"id": "trm_4a3fd79d0a1f6", "label": "salience attribution"},
        "domain": "Cognitive Systems",
    },
}


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
    assumptions: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineResult:
    """Structured result returned by :class:`SimulationEngine`."""

    scores: Dict[str, float]
    timepoints: list[float]
    trajectories: Dict[str, list[float]]
    module_summaries: Dict[str, Any]
    confidence: Dict[str, float]
    behavioral_tags: Dict[str, Dict[str, Any]]



REFERENCE_PATHWAY = load_reference_pathway()
REFERENCE_PATHWAY_NAME = REFERENCE_PATHWAY.get("pathway", "monoamine_neurotrophin_cascade")
REFERENCE_DOWNSTREAM_NODES = {str(key): float(value) for key, value in REFERENCE_PATHWAY.get("downstream_nodes", {}).items()}
REFERENCE_REGIONS, REFERENCE_CONNECTIVITY = load_reference_connectivity()

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

        downstream_nodes = dict(REFERENCE_DOWNSTREAM_NODES or {"CREB": 0.18, "BDNF": 0.09, "mTOR": 0.05})
        trkb_facilitation = request.assumptions.get("trkB_facilitation", request.regimen == "chronic")
        if trkb_facilitation:
            downstream_nodes["BDNF"] = downstream_nodes.get("BDNF", 0.1) * 1.35
            downstream_nodes["mTOR"] = downstream_nodes.get("mTOR", 0.05) * 1.25
            downstream_nodes["CREB"] = downstream_nodes.get("CREB", 0.18) * 1.15
            behaviour_axes["social_affiliation"] = behaviour_axes.get("social_affiliation", 0.0) + 0.15
            behaviour_axes["motivation"] = behaviour_axes.get("motivation", 0.0) + 0.12
        alpha2a_gate = request.assumptions.get("alpha2a_hcn_closure", False)
        if alpha2a_gate or "ADRA2A" in canonical_entries:
            behaviour_axes["cognitive_flexibility"] = behaviour_axes.get("cognitive_flexibility", 0.0) + 0.18
            behaviour_axes["exploration"] = behaviour_axes.get("exploration", 0.0) - 0.14
        molecular_params = MolecularCascadeParams(
            pathway=REFERENCE_PATHWAY_NAME,
            receptor_states=receptor_states,
            receptor_weights=receptor_weights,
            receptor_evidence=receptor_evidence,
            downstream_nodes=downstream_nodes,
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

        region_curves_raw = pkpd_profile.summary.get("region_brain_concentration", {})
        region_curves: Dict[str, list[float]] = {}
        for region, series in region_curves_raw.items():
            try:
                region_curves[region] = [float(value) for value in series]
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue
        region_terminal = {region: values[-1] for region, values in region_curves.items() if values}
        max_region_exposure = max(region_terminal.values(), default=1e-3)
        if max_region_exposure <= 0:
            max_region_exposure = 1e-3
        region_scalars = {
            region: float(max(0.2, min(1.8, exposure / max_region_exposure)))
            for region, exposure in region_terminal.items()
        }

        serotonin_mod = region_scalars.get("prefrontal", 1.0)
        dopamine_mod = region_scalars.get("striatum", 1.0)
        limbic_mod = region_scalars.get("amygdala", 1.0)

        serotonin_drive = float(np.tanh(molecular_result.summary["steady_state"] * (0.9 + 0.4 * serotonin_mod)))
        dopamine_drive = float(
            np.tanh(molecular_result.summary["transient_peak"] * (0.85 + 0.35 * dopamine_mod) * (1.0 - request.pvt_weight * 0.25))
        )
        noradrenaline_drive = float(np.tanh(molecular_result.summary["activation_index"] * 0.45 * (0.9 + 0.3 * limbic_mod)))

        if request.adhd:
            dopamine_drive *= 0.85
            noradrenaline_drive *= 0.9
        if request.gut_bias:
            serotonin_drive *= 1.05

        if trkb_facilitation:
            serotonin_drive *= 1.08
            dopamine_drive *= 1.05
        if alpha2a_gate:
            noradrenaline_drive *= 1.1
            dopamine_drive *= 0.95

        serotonin_drive = float(np.clip(serotonin_drive, -1.0, 1.0))
        dopamine_drive = float(np.clip(dopamine_drive, -1.0, 1.0))
        noradrenaline_drive = float(np.clip(noradrenaline_drive, -1.0, 1.0))

        auc_scaled = float(np.tanh(pkpd_profile.summary["auc"] / 100.0))
        base_regions = tuple(REFERENCE_REGIONS) if REFERENCE_REGIONS else ("prefrontal", "striatum", "amygdala")
        connectivity: MutableMapping[tuple[str, str], float] = {}
        base_matrix = np.asarray(REFERENCE_CONNECTIVITY, dtype=float)
        for i, src in enumerate(base_regions):
            for j, dst in enumerate(base_regions):
                if src == dst:
                    continue
                base_weight = 0.0
                if base_matrix.size and i < base_matrix.shape[0] and j < base_matrix.shape[1]:
                    base_weight = float(base_matrix[i, j])
                region_scale = 0.5 * (region_scalars.get(src, 1.0) + region_scalars.get(dst, 1.0))
                dynamic = 0.25 * auc_scaled
                connectivity[(src, dst)] = float(max(0.0, base_weight * (0.8 + 0.4 * region_scale) + dynamic))

        coupling_baseline = 0.25 + 0.4 * auc_scaled
        if trkb_facilitation:
            coupling_baseline += 0.05
        if alpha2a_gate:
            coupling_baseline += 0.03

        circuit_params = CircuitParameters(
            regions=base_regions,
            connectivity=connectivity,
            neuromodulator_drive={
                "serotonin": serotonin_drive,
                "dopamine": dopamine_drive,
                "noradrenaline": noradrenaline_drive,
            },
            regimen=request.regimen,
            timepoints=timepoints,
            coupling_baseline=coupling_baseline,
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
        for region, series in region_curves.items():
            trajectories[f"exposure_{region.lower()}"] = list(series)
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
        if request.assumptions:
            module_summaries["assumptions"] = dict(request.assumptions)
        if region_scalars:
            module_summaries["region_exposure_scalars"] = region_scalars
        if behaviour_axes:
            module_summaries["behavioural_axes"] = behaviour_axes

        behavioral_tags: Dict[str, Dict[str, Any]] = {}
        for metric in scores:
            annotation = BEHAVIORAL_TAG_MAP.get(metric)
            if annotation is None:
                continue
            normalized: Dict[str, Any] = {}
            for key, value in annotation.items():
                if isinstance(value, dict):
                    normalized[key] = dict(value)
                else:
                    normalized[key] = value
            behavioral_tags[metric] = normalized
        if behavioral_tags:
            module_summaries["behavioral_tags"] = behavioral_tags

        return EngineResult(
            scores=scores,
            timepoints=timepoints.astype(float).tolist(),
            trajectories=trajectories,
            module_summaries=module_summaries,
            confidence=confidence,
            behavioral_tags=behavioral_tags,
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
