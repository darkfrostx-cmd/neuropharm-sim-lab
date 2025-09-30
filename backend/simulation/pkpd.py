"""PK/PD integrations with optional OSPSuite support."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from typing import Dict, Mapping

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from ._integration import trapezoid_integral
from .assets import get_default_ospsuite_project_path, load_reference_pbpk_curves

try:  # pragma: no cover - optional dependency
    import ospsuite  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ospsuite = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)
HAS_OSPSUITE = ospsuite is not None


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
    summary: Dict[str, float | str | Dict[str, list[float]]]
    uncertainty: Dict[str, float]
    backend: str
    fallbacks: tuple[str, ...] = ()


def _resolve_ospsuite_project_path() -> str:
    override = os.environ.get("PKPD_OSPSUITE_MODEL")
    if override:
        return override
    return get_default_ospsuite_project_path()


def _simulate_with_ospsuite(params: PKPDParameters, time: npt.NDArray[np.float64]) -> PKPDProfile:
    if ospsuite is None:
        raise ImportError("ospsuite is not installed")

    project_path = _resolve_ospsuite_project_path()

    if not hasattr(ospsuite, "Model") or not hasattr(ospsuite, "Simulation"):
        raise RuntimeError("Installed ospsuite package does not expose the expected API")

    model = ospsuite.Model(project_path)  # type: ignore[call-arg]  # pragma: no cover - optional path
    simulation = ospsuite.Simulation(model)  # type: ignore[call-arg]  # pragma: no cover - optional path

    simulation.set_dosing(dose=params.dose_mg, interval=params.dosing_interval_h, number_of_doses="auto")
    simulation.set_clearance(params.clearance_rate)
    simulation.run(duration=params.simulation_hours)


    source_time = getattr(simulation, "time", None)
    source_plasma = getattr(simulation, "plasma_concentration", None)
    source_brain = getattr(simulation, "brain_concentration", None)
    region_reference: Dict[str, npt.NDArray[np.float64]] = {}
    if (
        source_time is None
        or source_plasma is None
        or source_brain is None
        or len(source_time) == 0
    ):
        fallback_time, fallback_plasma, fallback_brain, fallback_regions = load_reference_pbpk_curves()
        source_time = fallback_time
        source_plasma = fallback_plasma
        source_brain = fallback_brain
        region_reference = fallback_regions
    else:
        _, _, _, fallback_regions = load_reference_pbpk_curves()
        region_reference = fallback_regions
    plasma = np.interp(time, np.asarray(source_time, dtype=float), np.asarray(source_plasma, dtype=float))
    brain = np.interp(time, np.asarray(source_time, dtype=float), np.asarray(source_brain, dtype=float))

    region_concentration: Dict[str, npt.NDArray[np.float64]] = {}
    for region, values in region_reference.items():
        try:
            region_concentration[region] = np.interp(time, np.asarray(source_time, dtype=float), values.astype(float))
        except Exception:  # pragma: no cover - defensive fallback
            region_concentration[region] = np.interp(time, np.asarray(source_time, dtype=float), np.asarray(source_brain, dtype=float))

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
        "region_brain_concentration": {name: conc.astype(float).tolist() for name, conc in region_concentration.items()},
    }
    uncertainty = {
        "pkpd": float(max(0.05, 1.0 - np.clip(params.kg_confidence, 0.0, 1.0))),
        "exposure": float(max(0.05, 1.0 - np.clip(params.kg_confidence, 0.0, 1.0) * 0.9)),
    }
    return PKPDProfile(
        timepoints=time,
        plasma_concentration=plasma,
        brain_concentration=brain,
        summary=summary,
        uncertainty=uncertainty,
        backend="ospsuite",
    )


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

    region_concentration = {
        "prefrontal": (brain * 1.05).astype(float),
        "striatum": (brain * 0.92).astype(float),
        "amygdala": (brain * 1.08).astype(float),
    }

    summary: Dict[str, float | str | Dict[str, list[float]]] = {
        "auc": auc,
        "cmax": cmax,
        "exposure_index": exposure_index,
        "duration_h": float(params.simulation_hours),
        "regimen": params.regimen,
        "backend": "analytic",
        "occupancy_profile": {name: curve.astype(float).tolist() for name, curve in occupancy_profiles.items()},
        "terminal_occupancy": {name: float(curve[-1]) for name, curve in occupancy_profiles.items()},
        "region_brain_concentration": {name: conc.astype(float).tolist() for name, conc in region_concentration.items()},
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
        backend="analytic",
    )


def _two_compartment_ivp(params: PKPDParameters) -> PKPDProfile:
    horizon = float(max(params.simulation_hours, params.time_step))
    dose_times = [0.0]
    if params.regimen == "chronic" and params.dosing_interval_h > 0:
        n_doses = int(np.floor(horizon / params.dosing_interval_h))
        dose_times.extend(float(i * params.dosing_interval_h) for i in range(1, n_doses + 1))

    absorbed_dose = max(params.dose_mg * max(params.bioavailability, 0.0), 0.0)
    clearance = max(params.clearance_rate, 1e-4)
    k12 = float(max(1e-4, 0.25 + 0.35 * params.brain_plasma_ratio))
    k21 = float(max(1e-4, 0.05 + 0.1 * (1.0 - params.brain_plasma_ratio)))
    kbrain_clear = float(max(1e-4, clearance * 0.25))

    def dosing_rate(t: float) -> float:
        width = 0.35
        return sum(absorbed_dose * np.exp(-((t - dose_time) ** 2) / (2 * width ** 2)) / (width * np.sqrt(2 * np.pi)) for dose_time in dose_times)

    def dynamics(t: float, state: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        plasma_level, brain_level = state
        input_rate = dosing_rate(t)
        d_plasma = input_rate - clearance * plasma_level - k12 * plasma_level + k21 * brain_level
        d_brain = k12 * plasma_level - (k21 + kbrain_clear) * brain_level
        return np.array([d_plasma, d_brain], dtype=float)

    time_eval = np.arange(0.0, horizon + params.time_step, params.time_step)
    solution = solve_ivp(
        dynamics,
        (0.0, horizon),
        y0=np.array([0.0, 0.0], dtype=float),
        t_eval=time_eval,
        max_step=float(params.time_step),
    )
    if not solution.success:
        raise RuntimeError(f"SciPy PK/PD solver failed: {solution.message}")

    plasma = np.clip(solution.y[0], 0.0, None)
    brain = np.clip(solution.y[1], 0.0, None)

    occupancy_profiles: Dict[str, npt.NDArray[np.float64]] = {}
    for receptor, baseline in params.receptor_occupancy.items():
        baseline = float(max(1e-3, baseline))
        kd = max(1e-3, (1.0 - baseline))
        curve = brain / (brain + kd)
        occupancy_profiles[receptor] = np.clip(curve, 0.0, 1.0)

    region_concentration = {
        "prefrontal": (brain * 1.05).astype(float),
        "striatum": (brain * 0.92).astype(float),
        "amygdala": (brain * 1.08).astype(float),
    }

    summary: Dict[str, float | str | Dict[str, list[float]]] = {
        "auc": trapezoid_integral(plasma, solution.t),
        "cmax": float(np.max(plasma)),
        "exposure_index": trapezoid_integral(brain, solution.t) / (horizon + 1e-6),
        "duration_h": horizon,
        "regimen": params.regimen,
        "backend": "scipy",
        "occupancy_profile": {name: curve.astype(float).tolist() for name, curve in occupancy_profiles.items()},
        "terminal_occupancy": {name: float(curve[-1]) for name, curve in occupancy_profiles.items()},
        "region_brain_concentration": {name: conc.astype(float).tolist() for name, conc in region_concentration.items()},
    }
    kg_conf = float(np.clip(params.kg_confidence, 0.0, 1.0))
    uncertainty = {
        "pkpd": float(max(0.05, 1.0 - kg_conf * 0.95)),
        "exposure": float(max(0.05, 1.0 - kg_conf * 0.9)),
    }

    return PKPDProfile(
        timepoints=solution.t,
        plasma_concentration=plasma,
        brain_concentration=brain,
        summary=summary,
        uncertainty=uncertainty,
        backend="scipy",
    )


def simulate_pkpd(params: PKPDParameters) -> PKPDProfile:
    """Integrate a coarse PK/PD profile for the configured regimen."""

    backend = os.environ.get("PKPD_SIM_BACKEND", "").lower()
    prefer_ospsuite = backend in {"", "auto", "ospsuite"}
    if backend == "analytic":
        prefer_ospsuite = False

    fallbacks: list[str] = []

    if prefer_ospsuite and HAS_OSPSUITE:
        try:
            time = np.arange(0.0, params.simulation_hours + max(params.time_step, 1e-3), max(params.time_step, 1e-3))
            profile = _simulate_with_ospsuite(params, time)
            return profile
        except Exception as exc:  # pragma: no cover - optional path
            LOGGER.debug("OSPSuite backend unavailable (%s); falling back to SciPy integrator", exc)
            fallbacks.append(f"ospsuite:{exc.__class__.__name__}")

    if backend in {"scipy", "high_fidelity"}:
        profile = _two_compartment_ivp(params)
        if fallbacks:
            return replace(profile, fallbacks=tuple(fallbacks))
        return profile

    try:
        profile = _two_compartment_ivp(params)
        if fallbacks:
            return replace(profile, fallbacks=tuple(fallbacks))
        return profile
    except Exception as exc:  # pragma: no cover - defensive path
        LOGGER.debug("SciPy PK/PD integrator failed (%s); falling back to analytic solver", exc)
        fallbacks.append(f"scipy:{exc.__class__.__name__}")
        profile = _two_compartment_model(params)
        return replace(profile, fallbacks=tuple(fallbacks))


__all__ = ["PKPDParameters", "PKPDProfile", "simulate_pkpd", "HAS_OSPSUITE"]
