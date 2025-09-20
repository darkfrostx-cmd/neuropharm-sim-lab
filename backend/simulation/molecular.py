"""Interfaces for receptor and intracellular cascade simulations.

This module provides a deterministic surrogate for the PySB models that would
normally capture ligand–receptor interactions and downstream signalling
cascades.  The goal is to expose a stable, typed contract for higher level
orchestration code and unit tests.  The actual PySB models can be swapped in by
replacing :func:`simulate_molecular_layer` with a wrapper that calls the
pre‑compiled models once they are available in the deployment environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence, Literal
import math


ExposureMode = Literal["acute", "chronic"]


@dataclass(frozen=True)
class LigandContext:
    """Contextual information for a single receptor–ligand pairing."""

    receptor: str
    occupancy: float
    mechanism_factor: float
    ki_nm: float
    expression: float


@dataclass(frozen=True)
class MolecularConfig:
    """Configuration for the molecular layer simulation."""

    time: Sequence[float]
    ligands: Mapping[str, LigandContext]
    exposure: ExposureMode
    propagate_uncertainty: bool = True


@dataclass
class MolecularResult:
    """Time-resolved receptor activity and signalling readouts."""

    time: list[float]
    receptor_activity: Dict[str, list[float]]
    cascade_activity: Dict[str, list[float]]
    uncertainty: Dict[str, float]


def _validate_time_axis(time: Sequence[float]) -> None:
    if not time:
        raise ValueError("time axis must contain at least one element")
    previous = time[0]
    for t in time[1:]:
        if t < previous:
            raise ValueError("time axis must be monotonically increasing")
        previous = t


def simulate_molecular_layer(config: MolecularConfig) -> MolecularResult:
    """Simulate receptor occupancy cascades using analytic surrogates.

    Parameters
    ----------
    config:
        Dataclass containing ligand contexts and the simulation horizon.

    Returns
    -------
    MolecularResult
        A structure containing receptor level activity, aggregate cascade
        activity, and analytic uncertainty estimates.
    """

    _validate_time_axis(config.time)

    receptor_activity: Dict[str, list[float]] = {}
    uncertainties: Dict[str, float] = {}

    if not config.ligands:
        cascade = [0.0 for _ in config.time]
    else:
        cascade = [0.0 for _ in config.time]

    tau = 45.0 if config.exposure == "acute" else 180.0
    adaptation = 1.0 if config.exposure == "acute" else 1.2

    for name, ctx in config.ligands.items():
        affinity_scale = 1.0 / (1.0 + (ctx.ki_nm / 10.0))
        amplitude = ctx.expression * ctx.occupancy * ctx.mechanism_factor
        amplitude *= affinity_scale * adaptation
        trace = [float(amplitude * (1.0 - math.exp(-t / tau))) for t in config.time]
        receptor_activity[name] = trace
        for idx, value in enumerate(trace):
            cascade[idx] += value
        base_unc = abs(amplitude) * 0.05 if config.propagate_uncertainty else 0.0
        uncertainties[name] = max(0.01, base_unc)

    if receptor_activity:
        n = float(len(receptor_activity))
        cascade = [val / n for val in cascade]

    global_uncertainty = (
        sum(uncertainties.values()) / len(uncertainties) if uncertainties else 0.01
    )
    uncertainties["global"] = global_uncertainty

    cascade_activity = {"net_serotonin_modulation": cascade}

    return MolecularResult(
        time=list(config.time),
        receptor_activity=receptor_activity,
        cascade_activity=cascade_activity,
        uncertainty=uncertainties,
    )
