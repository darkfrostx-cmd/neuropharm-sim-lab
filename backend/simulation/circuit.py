"""TVB-inspired neural circuit coupling placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence, Tuple

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class CircuitParameters:
    """Parameters for the Virtual Brain style coupling step."""

    regions: Sequence[str]
    connectivity: Mapping[Tuple[str, str], float]
    neuromodulator_drive: Mapping[str, float]
    regimen: str
    timepoints: Sequence[float]
    coupling_baseline: float
    kg_confidence: float


@dataclass(frozen=True)
class CircuitResponse:
    """Outputs from the circuit integration."""

    timepoints: npt.NDArray[np.float64]
    region_activity: Dict[str, npt.NDArray[np.float64]]
    global_metrics: Dict[str, float]
    uncertainty: Dict[str, float]


def simulate_circuit_response(params: CircuitParameters) -> CircuitResponse:
    """Integrate a coarse network response with neuromodulator drives."""

    if len(params.timepoints) == 0:
        raise ValueError("timepoints must contain at least one value")

    time = np.asarray(params.timepoints, dtype=float)
    if np.any(np.diff(time) <= 0):
        raise ValueError("timepoints must be strictly increasing")

    serotonin_drive = params.neuromodulator_drive.get("serotonin", 0.0)
    dopamine_drive = params.neuromodulator_drive.get("dopamine", 0.0)
    noradrenaline_drive = params.neuromodulator_drive.get("noradrenaline", 0.0)

    drive_gain = params.coupling_baseline + 0.6 * serotonin_drive + 0.3 * dopamine_drive + 0.2 * noradrenaline_drive
    drive_gain = max(drive_gain, 1e-3)
    regimen_gain = 1.15 if params.regimen == "chronic" else 1.0

    region_activity: Dict[str, npt.NDArray[np.float64]] = {}
    for region in params.regions:
        coupling_sum = sum(params.connectivity.get((region, other), 0.0) for other in params.regions)
        effective_gain = drive_gain + 0.4 * coupling_sum
        effective_gain = max(effective_gain, 1e-3)
        response = effective_gain * (1.0 - np.exp(-0.12 * (time - time[0]))) * regimen_gain
        region_activity[region] = response.astype(float, copy=False)

    stacked = np.vstack(list(region_activity.values()))
    mean_activity = stacked.mean(axis=0)
    variance = stacked.var(axis=0)

    drive_index = float(np.clip(mean_activity[-1] / (1.0 + mean_activity[-1]), 0.0, 1.0))
    flexibility_index = float(np.clip(np.mean(variance) * 0.5, 0.0, 1.0))
    anxiety_index = float(np.clip(0.4 - 0.2 * serotonin_drive + 0.1 * noradrenaline_drive, 0.0, 1.0))
    apathy_index = float(np.clip(1.0 - drive_index * 0.85, 0.0, 1.0))

    uncertainty = {
        "network": float(max(0.05, 1.0 - np.clip(params.kg_confidence, 0.0, 1.0))),
    }
    global_metrics = {
        "drive_index": drive_index,
        "flexibility_index": flexibility_index,
        "anxiety_index": anxiety_index,
        "apathy_index": apathy_index,
    }

    return CircuitResponse(
        timepoints=time,
        region_activity=region_activity,
        global_metrics=global_metrics,
        uncertainty=uncertainty,
    )
