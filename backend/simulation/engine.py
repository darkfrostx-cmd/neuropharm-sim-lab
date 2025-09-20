"""Coordinator for the multiscale simulation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping

from ..engine.receptors import canonical_receptor_name, get_mechanism_factor
from .molecular import LigandContext, MolecularConfig, MolecularResult
from .molecular import simulate_molecular_layer
from .molecular import ExposureMode
from .pkpd import PKPDConfig, PKPDResult, simulate_pkpd
from .circuit import CircuitConfig, CircuitResult, simulate_circuit


KG_RECEPTOR_PARAMETERS: Mapping[str, Mapping[str, object]] = {
    "5-HT1A": {
        "ki_nm": 1.4,
        "expression": 0.9,
        "region_weights": {"PFC": -0.2, "Hippocampus": 0.3, "Amygdala": -0.25},
    },
    "5-HT1B": {
        "ki_nm": 3.0,
        "expression": 0.65,
        "region_weights": {"Striatum": -0.3, "VTA": -0.2},
    },
    "5-HT2A": {
        "ki_nm": 2.0,
        "expression": 0.8,
        "region_weights": {"PFC": 0.45, "Hippocampus": 0.2},
    },
    "5-HT2C": {
        "ki_nm": 4.5,
        "expression": 0.7,
        "region_weights": {"Striatum": -0.4, "VTA": -0.25},
    },
    "5-HT3": {
        "ki_nm": 8.0,
        "expression": 0.5,
        "region_weights": {"PFC": -0.3, "Amygdala": 0.25},
    },
    "5-HT7": {
        "ki_nm": 6.0,
        "expression": 0.6,
        "region_weights": {"Thalamus": 0.4, "Hippocampus": 0.3},
    },
    "MT2": {
        "ki_nm": 12.0,
        "expression": 0.4,
        "region_weights": {"Thalamus": 0.5, "Hippocampus": 0.2},
    },
}

DEFAULT_REGION_BASELINE: Dict[str, float] = {
    "PFC": 0.1,
    "Striatum": 0.12,
    "VTA": 0.1,
    "Hippocampus": 0.08,
    "Amygdala": 0.07,
    "Thalamus": 0.09,
}

DEFAULT_CONNECTIVITY: Mapping[str, Mapping[str, float]] = {
    "PFC": {"Striatum": 0.3, "Hippocampus": 0.2},
    "Striatum": {"PFC": 0.2, "VTA": 0.3},
    "VTA": {"Striatum": 0.25},
    "Hippocampus": {"PFC": 0.15, "Thalamus": 0.1},
    "Amygdala": {"PFC": 0.1},
    "Thalamus": {"PFC": 0.05},
}


@dataclass(frozen=True)
class ReceptorInput:
    """User supplied receptor state derived from the knowledge graph."""

    occupancy: float
    mechanism: str


@dataclass(frozen=True)
class SimulationConfig:
    """Top level configuration consumed by :func:`run_multiscale_pipeline`."""

    receptors: Mapping[str, ReceptorInput]
    exposure: ExposureMode
    adhd: bool = False
    gut_bias: bool = False
    pvt_weight: float = 0.5
    propagate_uncertainty: bool = True


@dataclass
class MultiscaleResult:
    """Composite result for the multi-layer simulation."""

    time: list[float]
    molecular: MolecularResult
    pkpd: PKPDResult
    circuit: CircuitResult
    behavioural_scores: Dict[str, float]
    uncertainty_breakdown: Dict[str, Dict[str, float]]


def _time_axis() -> list[float]:
    return [float(t) for t in range(0, 241, 10)]


def _build_ligand_contexts(config: SimulationConfig) -> tuple[Dict[str, LigandContext], Dict[str, float]]:
    ligands: Dict[str, LigandContext] = {}
    region_modulation: Dict[str, float] = {region: 0.0 for region in DEFAULT_REGION_BASELINE}

    for name, rec_input in config.receptors.items():
        canon = canonical_receptor_name(name)
        params = KG_RECEPTOR_PARAMETERS.get(canon)
        if not params:
            continue
        mechanism_factor = get_mechanism_factor(rec_input.mechanism)
        ligands[canon] = LigandContext(
            receptor=canon,
            occupancy=rec_input.occupancy,
            mechanism_factor=mechanism_factor,
            ki_nm=float(params["ki_nm"]),
            expression=float(params["expression"]),
        )
        region_weights = params.get("region_weights", {})
        for region, weight in region_weights.items():
            region_modulation[region] = region_modulation.get(region, 0.0) + (
                mechanism_factor * rec_input.occupancy * float(weight)
            )

    return ligands, region_modulation


def _adjust_baselines(config: SimulationConfig) -> Dict[str, float]:
    baseline = dict(DEFAULT_REGION_BASELINE)
    if config.adhd:
        baseline["Striatum"] = baseline.get("Striatum", 0.0) - 0.03
        baseline["PFC"] = baseline.get("PFC", 0.0) + 0.02
    if config.gut_bias:
        for region in ("Hippocampus", "Thalamus"):
            baseline[region] = baseline.get(region, 0.0) + 0.02
    return baseline


def run_multiscale_pipeline(config: SimulationConfig) -> MultiscaleResult:
    """Execute the molecular → PKPD → circuit pipeline and summarise behaviour."""

    time_axis = _time_axis()
    ligands, region_modulation = _build_ligand_contexts(config)

    molecular = simulate_molecular_layer(
        MolecularConfig(
            time=time_axis,
            ligands=ligands,
            exposure=config.exposure,
            propagate_uncertainty=config.propagate_uncertainty,
        )
    )

    clearance = 6.0 if config.exposure == "acute" else 12.0
    bioavailability = 0.5 + (0.25 * max(0.0, min(1.0, config.pvt_weight)))

    pkpd = simulate_pkpd(
        PKPDConfig(
            time=time_axis,
            exposure=config.exposure,
            propagate_uncertainty=config.propagate_uncertainty,
            clearance_half_life_hr=clearance,
            bioavailability=bioavailability,
        ),
        molecular,
    )

    baseline = _adjust_baselines(config)

    circuit = simulate_circuit(
        CircuitConfig(
            time=time_axis,
            exposure=config.exposure,
            region_baseline=baseline,
            region_modulation=region_modulation,
            connectivity=DEFAULT_CONNECTIVITY,
            propagate_uncertainty=config.propagate_uncertainty,
        ),
        pkpd,
    )

    scores = dict(circuit.behavioural_summary)

    if config.adhd:
        scores["DriveInvigoration"] = max(0.0, scores["DriveInvigoration"] - 5.0)
        scores["Motivation"] = max(0.0, scores["Motivation"] - 4.0)
    if config.gut_bias:
        scores["ApathyBlunting"] = min(100.0, scores["ApathyBlunting"] + 3.0)
    if config.exposure == "chronic":
        scores["SleepQuality"] = min(100.0, scores["SleepQuality"] + 2.0)

    uncertainty_breakdown: Dict[str, Dict[str, float]] = {
        "molecular": dict(molecular.uncertainty),
        "pkpd": dict(pkpd.uncertainty),
        "circuit": dict(circuit.uncertainty),
        "regions": dict(circuit.region_uncertainty),
        "combined": {},
    }

    for metric in scores:
        combined = (
            circuit.uncertainty.get(metric, 0.0)
            + pkpd.uncertainty.get("effect_site", 0.0)
            + molecular.uncertainty.get("global", 0.0)
        )
        uncertainty_breakdown["combined"][metric] = combined

    return MultiscaleResult(
        time=time_axis,
        molecular=molecular,
        pkpd=pkpd,
        circuit=circuit,
        behavioural_scores=scores,
        uncertainty_breakdown=uncertainty_breakdown,
    )
