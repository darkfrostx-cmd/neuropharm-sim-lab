"""Simplified PK/PD interface bridging to Open Systems Pharmacology or PBPK tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class PKPDParameters:
    """Inputs describing the dosing scenario and physiological priors."""

    compound: str
    dose_mg: float
    dosing_interval_h: float
    regimen: str  # "acute" or "chronic"
    clearance_rate: float
    bioavailability: float
    brain_plasma_ratio: float
    receptor_occupancy: Mapping[str, float]
    kg_confidence: float
    simulation_hours: float
    time_step: float = 1.0


@dataclass(frozen=True)
class PKPDProfile:
    """Output profile for PK/PD simulations."""

    timepoints: npt.NDArray[np.float64]
    plasma_concentration: npt.NDArray[np.float64]
    brain_concentration: npt.NDArray[np.float64]
    summary: Dict[str, float]
    uncertainty: Dict[str, float]


def simulate_pkpd(params: PKPDParameters) -> PKPDProfile:
    """Integrate a coarse PK/PD profile for the configured regimen."""

    step = max(params.time_step, 1e-3)
    time = np.arange(0.0, params.simulation_hours + step, step)
    kel = max(params.clearance_rate, 1e-3)
    dose = max(params.dose_mg, 0.0) * max(params.bioavailability, 0.0)

    plasma = dose * np.exp(-kel * time)
    if params.regimen == "chronic":
        max_doses = int(params.simulation_hours // params.dosing_interval_h)
        for n in range(1, max_doses + 1):
            start = n * params.dosing_interval_h
            mask = time >= start
            plasma = plasma + dose * np.exp(-kel * (time - start)) * mask
    brain = plasma * params.brain_plasma_ratio

    auc = float(np.trapezoid(plasma, time))
    cmax = float(np.max(plasma)) if plasma.size else 0.0
    exposure_index = float(np.trapezoid(brain, time) / (params.simulation_hours + 1e-6))

    uncertainty = {
        "pkpd": float(max(0.05, 1.0 - np.clip(params.kg_confidence, 0.0, 1.0))),
        "exposure": float(max(0.05, 1.0 - np.clip(params.kg_confidence, 0.0, 1.0) * 0.9)),
    }

    summary = {
        "auc": auc,
        "cmax": cmax,
        "exposure_index": exposure_index,
        "duration_h": float(params.simulation_hours),
        "regimen": params.regimen,
    }

    return PKPDProfile(
        timepoints=time,
        plasma_concentration=plasma,
        brain_concentration=brain,
        summary=summary,
        uncertainty=uncertainty,
    )
