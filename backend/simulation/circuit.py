"""Regional circuit simulations wrapping The Virtual Brain abstractions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence

from .molecular import ExposureMode
from .pkpd import PKPDResult


METRIC_REGION_WEIGHTS: Mapping[str, Mapping[str, float]] = {
    "drive": {"Striatum": 0.6, "VTA": 0.4},
    "apathy": {"Striatum": -0.5, "PFC": 0.3},
    "motivation": {"Striatum": 0.4, "PFC": 0.3, "Hippocampus": 0.3},
    "cognitive_flexibility": {"PFC": 0.6, "Hippocampus": 0.4},
    "anxiety": {"Amygdala": 0.6, "PFC": 0.2, "Hippocampus": -0.2},
    "sleep_quality": {"Thalamus": 0.5, "Hippocampus": 0.3, "PFC": -0.2},
}

SCORE_NAME_MAP: Mapping[str, str] = {
    "drive": "DriveInvigoration",
    "apathy": "ApathyBlunting",
    "motivation": "Motivation",
    "cognitive_flexibility": "CognitiveFlexibility",
    "anxiety": "Anxiety",
    "sleep_quality": "SleepQuality",
}


@dataclass(frozen=True)
class CircuitConfig:
    """Configuration for the TVB-based regional circuit simulation."""

    time: Sequence[float]
    exposure: ExposureMode
    region_baseline: Mapping[str, float]
    region_modulation: Mapping[str, float]
    connectivity: Mapping[str, Mapping[str, float]]
    propagate_uncertainty: bool = True


@dataclass
class CircuitResult:
    """Regional activity traces and behavioural summaries."""

    time: list[float]
    region_activity: Dict[str, list[float]]
    metric_traces: Dict[str, list[float]]
    behavioural_summary: Dict[str, float]
    uncertainty: Dict[str, float]
    region_uncertainty: Dict[str, float]


def simulate_circuit(config: CircuitConfig, pkpd: PKPDResult) -> CircuitResult:
    """Simulate mesoscale circuit dynamics using weighted surrogates."""

    time_axis = list(config.time)
    if len(time_axis) != len(pkpd.time):
        raise ValueError("Circuit time axis must match PKPD layer")

    region_names = set(config.region_baseline.keys()) | set(config.region_modulation.keys())
    for src, targets in config.connectivity.items():
        region_names.add(src)
        region_names.update(targets.keys())
    region_list = sorted(region_names)

    region_activity: Dict[str, list[float]] = {region: [] for region in region_list}

    connectivity = config.connectivity
    adaptation = 1.0 if config.exposure == "acute" else 1.15

    for idx, _ in enumerate(time_axis):
        effect = pkpd.effect_site[idx]
        for region in region_list:
            baseline = config.region_baseline.get(region, 0.0)
            modulation = config.region_modulation.get(region, 0.0)
            recurrent = sum(
                connectivity.get(region, {}).get(target, 0.0)
                * config.region_modulation.get(target, 0.0)
                for target in region_list
            )
            level = baseline + adaptation * (modulation * effect + 0.1 * recurrent)
            region_activity[region].append(level)

    metric_traces: Dict[str, list[float]] = {}
    for metric, weights in METRIC_REGION_WEIGHTS.items():
        trace: list[float] = []
        for t_idx in range(len(time_axis)):
            value = 0.0
            for region, weight in weights.items():
                series = region_activity.get(region)
                region_value = series[t_idx] if series else 0.0
                value += weight * region_value
            trace.append(value)
        metric_traces[metric] = trace

    behavioural_summary: Dict[str, float] = {}
    uncertainty: Dict[str, float] = {}
    for metric, trace in metric_traces.items():
        mean_val = sum(trace) / len(trace) if trace else 0.0
        score = 50.0 + (mean_val * 20.0)
        if metric == "apathy":
            score = 100.0 - score
        score = max(0.0, min(100.0, score))
        readable_name = SCORE_NAME_MAP[metric]
        behavioural_summary[readable_name] = score
        base_unc = abs(mean_val) * 0.1
        propagated = base_unc + pkpd.uncertainty.get("effect_site", 0.05)
        if not config.propagate_uncertainty:
            propagated *= 0.5
        uncertainty[readable_name] = propagated

    region_uncertainty = {}
    for region, series in region_activity.items():
        mean_val = sum(series) / len(series) if series else 0.0
        propagated = abs(mean_val) * 0.05 + pkpd.uncertainty.get("brain_concentration", 0.05)
        if not config.propagate_uncertainty:
            propagated *= 0.5
        region_uncertainty[region] = propagated

    uncertainty["global"] = sum(uncertainty.values()) / max(len(uncertainty), 1)

    return CircuitResult(
        time=time_axis,
        region_activity=region_activity,
        metric_traces=metric_traces,
        behavioural_summary=behavioural_summary,
        uncertainty=uncertainty,
        region_uncertainty=region_uncertainty,
    )
