"""PK/PD integrations with optional OSPSuite support."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, Mapping

import numpy as np
import numpy.typing as npt

from ._integration import trapezoid_integral

try:  # pragma: no cover - optional dependency
    import ospsuite  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ospsuite = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)


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
    summary: Dict[str, float | str]
    uncertainty: Dict[str, float]


def _simulate_with_ospsuite(params: PKPDParameters, time: npt.NDArray[np.float64]) -> PKPDProfile:
    if ospsuite is None:
        raise ImportError("ospsuite is not installed")

    project_path = os.environ.get("PKPD_OSPSUITE_MODEL")
    if not project_path:
        raise RuntimeError("Set PKPD_OSPSUITE_MODEL to point at a PK-Sim project")

    if not hasattr(ospsuite, "Model") or not hasattr(ospsuite, "Simulation"):
        raise RuntimeError("Installed ospsuite package does not expose the expected API")

    # The OSPSuite Python bindings expect a project model to be loaded before a
    # simulation can be executed.  We purposely keep this generic so users can
    # provide any PBPK model exported from PK-Sim.  When the environment is not
    # prepared (e.g. in CI), an informative error is raised to trigger the
    # analytic fallback.
    model = ospsuite.Model(project_path)  # type: ignore[call-arg]  # pragma: no cover - optional path
    simulation = ospsuite.Simulation(model)  # type: ignore[call-arg]  # pragma: no cover - optional path

    simulation.set_dosing(dose=params.dose_mg, interval=params.dosing_interval_h, number_of_doses="auto")
    simulation.set_clearance(params.clearance_rate)
    simulation.run(duration=params.simulation_hours)

    plasma = np.interp(time, simulation.time, simulation.plasma_concentration)
    brain = np.interp(time, simulation.time, simulation.brain_concentration)

    occupancy_profiles: Dict[str, npt.NDArray[np.float64]] = {}
    for receptor, baseline in params.receptor_occupancy.items():
        baseline = float(max(1e-3, baseline))
        kd = max(1e-3, (1.0 - baseline))
        curve = brain / (brain + kd)
        occupancy_profiles[receptor] = np.clip(curve, 0.0, 1.0)

    summary = {
        "auc": trapezoid_integral(plasma, time),
        "cmax": float(np.max(plasma)),
        "exposure_index": trapezoid_integral(brain, time) / (params.simulation_hours + 1e-6),
        "duration_h": float(params.simulation_hours),
        "regimen": params.regimen,
        "backend": "ospsuite",
        "occupancy_profile": {name: curve.astype(float).tolist() for name, curve in occupancy_profiles.items()},
        "terminal_occupancy": {name: float(curve[-1]) for name, curve in occupancy_profiles.items()},
    }
    uncertainty = {
        "pkpd": float(max(0.05, 1.0 - np.clip(params.kg_confidence, 0.0, 1.0))),
        "exposure": float(max(0.05, 1.0 - np.clip(params.kg_confidence, 0.0, 1.0) * 0.9)),
    }
    return PKPDProfile(timepoints=time, plasma_concentration=plasma, brain_concentration=brain, summary=summary, uncertainty=uncertainty)


def _two_compartment_model(params: PKPDParameters) -> PKPDProfile:
    step = float(max(params.time_step, 1e-3))
    if params.simulation_hours <= 0:
        raise ValueError("simulation_hours must be positive")

    n_steps = int(np.floor(params.simulation_hours / step)) + 1
    time = np.linspace(0.0, params.simulation_hours, n_steps)

    plasma = np.zeros(n_steps, dtype=float)
    brain = np.zeros(n_steps, dtype=float)

    absorbed_dose = max(params.dose_mg * max(params.bioavailability, 0.0), 0.0)
    dose_events = np.zeros(n_steps, dtype=float)
    dose_events[0] = absorbed_dose
    if params.regimen == "chronic":
        interval = max(int(round(params.dosing_interval_h / step)), 1)
        for idx in range(interval, n_steps, interval):
            dose_events[idx] += absorbed_dose

    clearance = max(params.clearance_rate, 1e-4)
    k12 = float(max(1e-4, 0.25 + 0.35 * params.brain_plasma_ratio))
    k21 = float(max(1e-4, 0.05 + 0.1 * (1.0 - params.brain_plasma_ratio)))
    kbrain_clear = float(max(1e-4, clearance * 0.25))

    plasma[0] = dose_events[0]
    brain[0] = plasma[0] * params.brain_plasma_ratio

    for idx in range(1, n_steps):
        dt = time[idx] - time[idx - 1]
        plasma_prev = plasma[idx - 1] + dose_events[idx]
        brain_prev = brain[idx - 1]
        dpdt = -clearance * plasma_prev - k12 * plasma_prev + k21 * brain_prev
        dbdt = k12 * plasma_prev - (k21 + kbrain_clear) * brain_prev
        plasma[idx] = max(0.0, plasma_prev + dt * dpdt)
        brain[idx] = max(0.0, brain_prev + dt * dbdt)

    auc = trapezoid_integral(plasma, time)
    cmax = float(np.max(plasma)) if plasma.size else 0.0
    exposure_index = trapezoid_integral(brain, time) / (params.simulation_hours + 1e-6)

    occupancy_profiles: Dict[str, npt.NDArray[np.float64]] = {}
    for receptor, baseline in params.receptor_occupancy.items():
        baseline = float(max(1e-3, baseline))
        kd = max(1e-3, (1.0 - baseline))
        curve = brain / (brain + kd)
        occupancy_profiles[receptor] = np.clip(curve, 0.0, 1.0)

    summary: Dict[str, float | str | Dict[str, list[float]]] = {
        "auc": auc,
        "cmax": cmax,
        "exposure_index": exposure_index,
        "duration_h": float(params.simulation_hours),
        "regimen": params.regimen,
        "backend": "analytic",
        "occupancy_profile": {name: curve.astype(float).tolist() for name, curve in occupancy_profiles.items()},
        "terminal_occupancy": {name: float(curve[-1]) for name, curve in occupancy_profiles.items()},
    }
    kg_conf = float(np.clip(params.kg_confidence, 0.0, 1.0))
    uncertainty = {
        "pkpd": float(max(0.05, 1.0 - kg_conf)),
        "exposure": float(max(0.05, 1.0 - kg_conf * 0.9)),
    }

    return PKPDProfile(
        timepoints=time,
        plasma_concentration=plasma,
        brain_concentration=brain,
        summary=summary,
        uncertainty=uncertainty,
    )


def simulate_pkpd(params: PKPDParameters) -> PKPDProfile:
    """Integrate a coarse PK/PD profile for the configured regimen."""

    backend = os.environ.get("PKPD_SIM_BACKEND", "").lower()
    if backend == "ospsuite":
        try:
            time = np.arange(0.0, params.simulation_hours + max(params.time_step, 1e-3), max(params.time_step, 1e-3))
            return _simulate_with_ospsuite(params, time)
        except Exception as exc:  # pragma: no cover - optional path
            LOGGER.debug("OSPSuite backend unavailable (%s); falling back to analytic integrator", exc)

    return _two_compartment_model(params)


__all__ = ["PKPDParameters", "PKPDProfile", "simulate_pkpd"]
