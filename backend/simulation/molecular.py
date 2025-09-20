"""PySB-integrated molecular cascade helpers.

The production system compiles PySB models straight from the knowledge graph.
Those models can be heavy and require optional dependencies, so the helpers in
this module provide a thin abstraction that:

* runs a rule-based cascade via :mod:`pysb` when the library is available;
* gracefully falls back to a deterministic analytic approximation when PySB is
  not installed (the default in CI);
* preserves the summary/uncertainty contract expected by the orchestration
  engine.

The public API is intentionally small so the heavy-weight models can be swapped
in without touching the callers.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, Mapping, Sequence

import numpy as np
import numpy.typing as npt

try:  # pragma: no cover - optional dependency
    from pysb import Initial, Model, Monomer, Observable, Parameter, Rule  # type: ignore
    from pysb.simulator import ScipyOdeSimulator  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Model = None  # type: ignore[assignment]
    Monomer = None  # type: ignore[assignment]
    Parameter = None  # type: ignore[assignment]
    Initial = None  # type: ignore[assignment]
    Rule = None  # type: ignore[assignment]
    Observable = None  # type: ignore[assignment]
    ScipyOdeSimulator = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MolecularCascadeParams:
    """Container for PySB cascade inputs."""

    pathway: str
    receptor_states: Mapping[str, float]
    receptor_weights: Mapping[str, float]
    receptor_evidence: Mapping[str, float]
    downstream_nodes: Mapping[str, float]
    stimulus: float
    timepoints: Sequence[float]


@dataclass(frozen=True)
class MolecularCascadeResult:
    """Result of a cascade simulation."""

    timepoints: npt.NDArray[np.float64]
    node_activity: Dict[str, npt.NDArray[np.float64]]
    summary: Dict[str, float | str]
    uncertainty: Dict[str, float]


def _aggregate_receptor_effect(params: MolecularCascadeParams) -> float:
    effect = 0.0
    for name, occ in params.receptor_states.items():
        weight = params.receptor_weights.get(name, 0.5)
        evidence = params.receptor_evidence.get(name, 0.5)
        effect += occ * weight * (0.5 + 0.5 * evidence)
    return float(effect * params.stimulus)


def _sanitize_identifier(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_")
    if not cleaned:
        cleaned = "Node"
    if cleaned[0].isdigit():
        cleaned = f"X_{cleaned}"
    return cleaned


def _simulate_with_pysb(
    params: MolecularCascadeParams,
    receptor_effect: float,
    time: npt.NDArray[np.float64],
) -> Dict[str, npt.NDArray[np.float64]]:
    if Model is None or Monomer is None or Parameter is None or Rule is None or ScipyOdeSimulator is None:
        raise ImportError("PySB is not installed")

    if not params.downstream_nodes:
        raise ValueError("at least one downstream node must be supplied")

    model = Model()
    with model:
        Monomer("Signal")
        Parameter("Signal_0", max(receptor_effect, 0.0))
        Initial(model.monomers["Signal"](), model.parameters["Signal_0"])
        Parameter("Signal_decay", 1e-3)
        Rule("Signal_autodecay", model.monomers["Signal"]() >> None, model.parameters["Signal_decay"])
        for node, rate in params.downstream_nodes.items():
            identifier = _sanitize_identifier(node)
            Monomer(identifier)
            Parameter(f"{identifier}_0", 0.0)
            Initial(model.monomers[identifier](), model.parameters[f"{identifier}_0"])
            Parameter(f"k_act_{identifier}", max(rate * max(receptor_effect, 0.1), 1e-4))
            Parameter(f"k_deg_{identifier}", max(rate * 0.15, 1e-4))
            Rule(
                f"activate_{identifier}",
                model.monomers["Signal"]() >> model.monomers["Signal"]() + model.monomers[identifier](),
                model.parameters[f"k_act_{identifier}"],
            )
            Rule(
                f"degrade_{identifier}",
                model.monomers[identifier]() >> None,
                model.parameters[f"k_deg_{identifier}"],
            )
            Observable(f"{identifier}_obs", model.monomers[identifier]())

    simulator = ScipyOdeSimulator(model, tspan=time)
    outcome = simulator.run()
    activity: Dict[str, npt.NDArray[np.float64]] = {}
    for node in params.downstream_nodes:
        identifier = _sanitize_identifier(node)
        obs_key = f"{identifier}_obs"
        activity[node] = np.asarray(outcome.observables[obs_key], dtype=float)
    return activity


def _simulate_analytic(
    params: MolecularCascadeParams,
    receptor_effect: float,
    time: npt.NDArray[np.float64],
) -> Dict[str, npt.NDArray[np.float64]]:
    if not params.downstream_nodes:
        raise ValueError("at least one downstream node must be supplied")
    activity: Dict[str, npt.NDArray[np.float64]] = {}
    start = float(time[0])
    delta = time - start
    for node, rate in params.downstream_nodes.items():
        rate = max(rate, 1e-3)
        response = receptor_effect * (1.0 - np.exp(-rate * delta))
        activity[node] = response.astype(float, copy=False)
    return activity


def simulate_cascade(params: MolecularCascadeParams) -> MolecularCascadeResult:
    """Compute a pathway response using PySB when available."""

    if len(params.timepoints) == 0:
        raise ValueError("timepoints must contain at least one value")

    time = np.asarray(params.timepoints, dtype=float)
    if np.any(np.diff(time) <= 0):
        raise ValueError("timepoints must be strictly increasing")

    receptor_effect = _aggregate_receptor_effect(params)

    backend = os.environ.get("MOLECULAR_SIM_BACKEND", "").lower()
    activity: Dict[str, npt.NDArray[np.float64]]
    backend_label = "analytic"
    if backend != "analytic" and Model is not None:
        try:
            activity = _simulate_with_pysb(params, receptor_effect, time)
            backend_label = "pysb"
        except Exception as exc:  # pragma: no cover - optional path
            LOGGER.debug("PySB cascade failed (%s); falling back to analytic backend", exc)
            activity = _simulate_analytic(params, receptor_effect, time)
    else:
        activity = _simulate_analytic(params, receptor_effect, time)

    stacked = np.vstack(list(activity.values()))
    mean_activity = stacked.mean(axis=0)

    transient_peak = float(np.max(mean_activity))
    steady_state = float(mean_activity[-1])
    auc = float(np.trapezoid(mean_activity, time))
    duration = float(time[-1] - time[0])
    activation_index = float(auc / duration) if duration > 0 else steady_state

    evidence_values = list(params.receptor_evidence.values()) or [0.5]
    mean_evidence = float(np.clip(np.mean(evidence_values), 0.0, 1.0))
    uncertainty_level = float(max(0.05, 1.0 - mean_evidence))
    if backend_label == "pysb":
        uncertainty_level *= 0.85

    summary: Dict[str, float | str] = {
        "transient_peak": transient_peak,
        "steady_state": steady_state,
        "activation_index": activation_index,
        "pathway": params.pathway,
        "backend": backend_label,
    }
    uncertainty = {
        "cascade": float(np.clip(uncertainty_level, 0.05, 0.99)),
        "steady_state": float(np.clip(uncertainty_level * 0.9, 0.05, 0.99)),
    }

    return MolecularCascadeResult(
        timepoints=time,
        node_activity=activity,
        summary=summary,
        uncertainty=uncertainty,
    )


__all__ = ["MolecularCascadeParams", "MolecularCascadeResult", "simulate_cascade"]
