"""High level simulation orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Literal

import numpy as np

from .circuit import CircuitParameters, simulate_circuit_response
from .molecular import MolecularCascadeParams, simulate_cascade
from .pkpd import PKPDParameters, simulate_pkpd

Mechanism = Literal["agonist", "antagonist", "partial", "inverse"]


@dataclass(frozen=True)
class ReceptorEngagement:
    """Normalised receptor engagement derived from the knowledge graph."""

    name: str
    occupancy: float
    mechanism: Mechanism
    kg_weight: float
    evidence: float


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


class SimulationEngine:
    """Coordinate the molecular, PK/PD, and circuit layers."""

    def __init__(self, time_step: float = 1.0) -> None:
        self.time_step = time_step

    def run(self, request: EngineRequest) -> EngineResult:
        """Execute the multi-layer simulation."""

        horizon = 24.0 if request.regimen == "acute" else 24.0 * 7
        timepoints = np.arange(0.0, horizon + self.time_step, self.time_step)

        receptor_states: Dict[str, float] = {
            name: engagement.occupancy for name, engagement in request.receptors.items()
        }
        receptor_weights: Dict[str, float] = {
            name: engagement.kg_weight for name, engagement in request.receptors.items()
        }
        receptor_evidence: Dict[str, float] = {
            name: engagement.evidence for name, engagement in request.receptors.items()
        }
        mean_evidence = float(np.mean(list(receptor_evidence.values()) or [0.5]))

        molecular_params = MolecularCascadeParams(
            pathway="monoamine_neurotrophin_cascade",
            receptor_states=receptor_states,
            receptor_weights=receptor_weights,
            receptor_evidence=receptor_evidence,
            downstream_nodes={"CREB": 0.18, "BDNF": 0.09, "mTOR": 0.05},
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
        for node, values in molecular_result.node_activity.items():
            trajectories[f"cascade_{node.lower()}"] = values.astype(float).tolist()
        for region, values in circuit_response.region_activity.items():
            trajectories[f"region_{region.lower()}"] = values.astype(float).tolist()

        module_summaries: Dict[str, Any] = {
            "molecular": molecular_result.summary,
            "pkpd": pkpd_profile.summary,
            "circuit": circuit_response.global_metrics,
        }

        return EngineResult(
            scores=scores,
            timepoints=timepoints.astype(float).tolist(),
            trajectories=trajectories,
            module_summaries=module_summaries,
            confidence=confidence,
        )
