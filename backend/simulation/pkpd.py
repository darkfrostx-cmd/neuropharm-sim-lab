"""PBPK/PKPD layer wrapping Open Systems Pharmacology style models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence
import math

from .molecular import ExposureMode, MolecularResult


@dataclass(frozen=True)
class PKPDConfig:
    """Configuration for the pharmacokinetic/pharmacodynamic layer."""

    time: Sequence[float]
    exposure: ExposureMode
    propagate_uncertainty: bool = True
    clearance_half_life_hr: float = 6.0
    bioavailability: float = 0.6


@dataclass
class PKPDResult:
    """Effect-site concentration time course and derived statistics."""

    time: list[float]
    brain_concentration: list[float]
    effect_site: list[float]
    uncertainty: Dict[str, float]


def simulate_pkpd(config: PKPDConfig, molecular: MolecularResult) -> PKPDResult:
    """Simulate a reduced PKPD model driven by molecular activity."""

    time_axis = list(config.time)

    if len(time_axis) != len(molecular.time):
        raise ValueError("PKPD time axis must match molecular layer")

    clearance_half_life = config.clearance_half_life_hr
    if config.exposure == "chronic":
        clearance_half_life *= 1.5
    elimination_constant = math.log(2.0) / max(clearance_half_life, 1e-3)

    brain_conc: list[float] = []
    effect_site: list[float] = []

    cascade = molecular.cascade_activity.get("net_serotonin_modulation", [0.0] * len(time_axis))

    previous = 0.0
    previous_time = time_axis[0]
    for idx, time_point in enumerate(time_axis):
        signal = cascade[idx]
        dt = time_point - previous_time if idx else 0.0
        previous_time = time_point
        delta = (signal * config.bioavailability) - (previous * elimination_constant * dt)
        level = previous + delta
        previous = level
        brain_conc.append(level)
        effect_site.append(level * 0.8)

    base_unc = molecular.uncertainty.get("global", 0.05)
    propagated_unc = base_unc * (0.5 if not config.propagate_uncertainty else 1.0)
    uncertainty = {
        "brain_concentration": propagated_unc,
        "effect_site": propagated_unc * 1.1,
    }

    return PKPDResult(
        time=time_axis,
        brain_concentration=brain_conc,
        effect_site=effect_site,
        uncertainty=uncertainty,
    )
