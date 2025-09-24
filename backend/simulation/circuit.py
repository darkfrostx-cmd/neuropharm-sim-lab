"""Circuit-level simulators with optional TVB integration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, Mapping, Sequence, Tuple

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from .assets import load_reference_connectivity

try:  # pragma: no cover - optional dependency
    from tvb.simulator.lab import (  # type: ignore
        connectivity,
        coupling,
        integrators,
        models,
        monitors,
        simulator,
    )
except Exception:  # pragma: no cover - optional dependency
    connectivity = None  # type: ignore[assignment]
    coupling = None  # type: ignore[assignment]
    integrators = None  # type: ignore[assignment]
    models = None  # type: ignore[assignment]
    monitors = None  # type: ignore[assignment]
    simulator = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)
HAS_TVB = all(module is not None for module in (connectivity, coupling, integrators, models, monitors, simulator))


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
    global_metrics: Dict[str, float | str]
    uncertainty: Dict[str, float]


def _simulate_with_tvb(params: CircuitParameters, time: npt.NDArray[np.float64]) -> CircuitResponse:
    if connectivity is None or models is None or simulator is None:
        raise ImportError("The Virtual Brain is not installed")

    n_regions = len(params.regions)
    if n_regions == 0:
        raise ValueError("at least one region is required")
    if len(time) < 2:
        raise ValueError("at least two timepoints are required for TVB integration")

    reference_regions, reference_weights = load_reference_connectivity()
    conn = connectivity.Connectivity()  # type: ignore[call-arg]  # pragma: no cover - optional path
    conn.number_of_regions = n_regions
    conn.region_labels = np.array(params.regions)
    weights = np.zeros((n_regions, n_regions), dtype=float)
    for (src, dst), value in params.connectivity.items():
        try:
            i = params.regions.index(src)
            j = params.regions.index(dst)
        except ValueError:
            continue
        weights[i, j] = value
    for src_index, src in enumerate(params.regions):
        for dst_index, dst in enumerate(params.regions):
            if src == dst:
                continue
            try:
                ref_src = reference_regions.index(src)
                ref_dst = reference_regions.index(dst)
                weights[src_index, dst_index] += float(reference_weights[ref_src, ref_dst])
            except ValueError:
                continue
    conn.weights = weights
    conn.tract_lengths = np.ones((n_regions, n_regions), dtype=float)
    conn.configure()

    model = models.Generic2dOscillator()  # type: ignore[call-arg]  # pragma: no cover
    model.tau = 1.0 + 0.4 * params.neuromodulator_drive.get("serotonin", 0.0)

    coupling_fn = coupling.Linear(a=params.coupling_baseline)  # type: ignore[call-arg]  # pragma: no cover
    dt = float(max(np.min(np.diff(time)), 1e-2))
    integrator = integrators.HeunDeterministic(dt=dt)  # type: ignore[call-arg]  # pragma: no cover
    monitor = monitors.TemporalAverage(period=max(dt * 10.0, 0.5))  # type: ignore[call-arg]  # pragma: no cover

    sim = simulator.Simulator(
        model=model,
        connectivity=conn,
        coupling=coupling_fn,
        integrator=integrator,
        monitors=(monitor,),
    )  # pragma: no cover - optional path
    sim.configure()

    total_duration = float(time[-1] - time[0])
    raw_output = sim.run(simulation_length=total_duration)  # pragma: no cover - optional path
    if not raw_output or raw_output[0][0] is None:
        raise RuntimeError("TVB simulation returned no data")

    tvb_time = np.array(raw_output[0][0], dtype=float)
    tvb_series = np.array(raw_output[0][1], dtype=float).squeeze()
    if tvb_series.ndim == 1:
        tvb_series = tvb_series[np.newaxis, :]

    region_activity: Dict[str, npt.NDArray[np.float64]] = {}
    for idx, region in enumerate(params.regions):
        interpolated = np.interp(time - time[0], tvb_time, tvb_series[idx])
        region_activity[region] = interpolated.astype(float)

    drive_index = float(np.clip(np.mean([activity[-1] for activity in region_activity.values()]), 0.0, 1.0))
    flexibility_index = float(np.clip(np.std(tvb_series), 0.0, 1.0))
    anxiety_index = float(np.clip(0.4 - 0.2 * params.neuromodulator_drive.get("serotonin", 0.0), 0.0, 1.0))
    apathy_index = float(np.clip(1.0 - drive_index * 0.8, 0.0, 1.0))

    summary: Dict[str, float | str] = {
        "drive_index": drive_index,
        "flexibility_index": flexibility_index,
        "anxiety_index": anxiety_index,
        "apathy_index": apathy_index,
        "backend": "tvb",
    }
    kg_conf = float(np.clip(params.kg_confidence, 0.0, 1.0))
    uncertainty = {"network": float(max(0.05, 1.0 - kg_conf))}

    return CircuitResponse(timepoints=time, region_activity=region_activity, global_metrics=summary, uncertainty=uncertainty)


def _simulate_analytic(params: CircuitParameters, time: npt.NDArray[np.float64]) -> CircuitResponse:
    if len(time) == 0:
        raise ValueError("timepoints must contain at least one value")
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

    stacked = np.vstack(list(region_activity.values())) if region_activity else np.zeros((1, len(time)))
    mean_activity = stacked.mean(axis=0)
    variance = stacked.var(axis=0)

    drive_index = float(np.clip(mean_activity[-1] / (1.0 + mean_activity[-1]), 0.0, 1.0))
    flexibility_index = float(np.clip(np.mean(variance) * 0.5, 0.0, 1.0))
    anxiety_index = float(np.clip(0.4 - 0.2 * serotonin_drive + 0.1 * noradrenaline_drive, 0.0, 1.0))
    apathy_index = float(np.clip(1.0 - drive_index * 0.85, 0.0, 1.0))

    summary: Dict[str, float | str] = {
        "drive_index": drive_index,
        "flexibility_index": flexibility_index,
        "anxiety_index": anxiety_index,
        "apathy_index": apathy_index,
        "backend": "analytic",
    }
    kg_conf = float(np.clip(params.kg_confidence, 0.0, 1.0))
    uncertainty = {"network": float(max(0.05, 1.0 - kg_conf))}

    return CircuitResponse(timepoints=time, region_activity=region_activity, global_metrics=summary, uncertainty=uncertainty)


def _simulate_with_scipy(params: CircuitParameters, time: npt.NDArray[np.float64]) -> CircuitResponse:
    if len(time) == 0:
        raise ValueError("timepoints must contain at least one value")

    regions = list(params.regions)
    n_regions = len(regions)
    if n_regions == 0:
        raise ValueError("at least one region is required")

    weights = np.zeros((n_regions, n_regions), dtype=float)
    for (src, dst), value in params.connectivity.items():
        try:
            i = regions.index(src)
            j = regions.index(dst)
        except ValueError:
            continue
        weights[i, j] = float(value)

    serotonin_drive = params.neuromodulator_drive.get("serotonin", 0.0)
    dopamine_drive = params.neuromodulator_drive.get("dopamine", 0.0)
    noradrenaline_drive = params.neuromodulator_drive.get("noradrenaline", 0.0)
    drive_vector = np.full(n_regions, params.coupling_baseline, dtype=float)
    drive_vector += 0.4 * serotonin_drive + 0.25 * dopamine_drive + 0.2 * noradrenaline_drive

    def dynamics(_: float, state: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        coupling_term = weights @ state - np.sum(weights, axis=1) * state
        damping = 0.1 + 0.05 * np.arange(n_regions)
        return drive_vector + coupling_term - damping * state

    solution = solve_ivp(
        dynamics,
        (float(time[0]), float(time[-1])),
        y0=np.zeros(n_regions, dtype=float),
        t_eval=time,
        max_step=float(np.min(np.diff(time)) if time.size > 1 else 1.0),
    )
    if not solution.success:
        raise RuntimeError(f"SciPy circuit solver failed: {solution.message}")

    region_activity: Dict[str, npt.NDArray[np.float64]] = {}
    for idx, region in enumerate(regions):
        region_activity[region] = np.clip(solution.y[idx], 0.0, None).astype(float)

    stacked = np.vstack(list(region_activity.values()))
    mean_activity = stacked.mean(axis=0)
    variance = stacked.var(axis=0)

    drive_index = float(np.clip(mean_activity[-1] / (1.0 + mean_activity[-1]), 0.0, 1.0))
    flexibility_index = float(np.clip(np.mean(variance) * 0.6, 0.0, 1.0))
    anxiety_index = float(np.clip(0.4 - 0.25 * serotonin_drive + 0.15 * noradrenaline_drive, 0.0, 1.0))
    apathy_index = float(np.clip(1.0 - drive_index * 0.9, 0.0, 1.0))

    summary: Dict[str, float | str] = {
        "drive_index": drive_index,
        "flexibility_index": flexibility_index,
        "anxiety_index": anxiety_index,
        "apathy_index": apathy_index,
        "backend": "scipy",
    }
    kg_conf = float(np.clip(params.kg_confidence, 0.0, 1.0))
    uncertainty = {"network": float(max(0.05, 1.0 - kg_conf * 0.95))}

    return CircuitResponse(timepoints=time, region_activity=region_activity, global_metrics=summary, uncertainty=uncertainty)


def simulate_circuit_response(params: CircuitParameters) -> CircuitResponse:
    """Integrate a coarse network response with neuromodulator drives."""

    time = np.asarray(params.timepoints, dtype=float)
    if len(time) == 0:
        raise ValueError("timepoints must contain at least one value")

    backend = os.environ.get("CIRCUIT_SIM_BACKEND", "").lower()
    prefer_tvb = backend in {"", "auto", "tvb"}
    if backend == "analytic":
        prefer_tvb = False

    if prefer_tvb and HAS_TVB:
        try:
            return _simulate_with_tvb(params, time)
        except Exception as exc:  # pragma: no cover - optional path
            LOGGER.debug("TVB backend unavailable (%s); falling back to analytic integrator", exc)

    if backend in {"scipy", "high_fidelity"}:
        return _simulate_with_scipy(params, time)

    try:
        return _simulate_with_scipy(params, time)
    except Exception as exc:  # pragma: no cover - defensive path
        LOGGER.debug("SciPy circuit solver failed (%s); falling back to analytic response", exc)
        return _simulate_analytic(params, time)


__all__ = ["CircuitParameters", "CircuitResponse", "simulate_circuit_response", "HAS_TVB"]
