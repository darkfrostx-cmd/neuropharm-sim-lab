"""PySB-inspired molecular cascade utilities.

The real project integrates PySB models compiled from the knowledge graph.  The
helpers defined here provide a typed, numerically stable placeholder that
accepts the same style of parameters: receptor occupancies derived from the
knowledge graph, weightings for each downstream node, and evidence/confidence
scores that quantify how trustworthy the pathway wiring is.  The placeholder
uses simple analytic solutions to keep the tests fast while exercising the
interfaces expected by the orchestration engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class MolecularCascadeParams:
    """Container for PySB cascade inputs.

    Parameters
    ----------
    pathway:
        Identifier of the signalling pathway being simulated.
    receptor_states:
        Mapping of receptor names to fractional occupancy (0-1 range).
    receptor_weights:
        Relative influence of each receptor on the pathway activation.
    receptor_evidence:
        Confidence scores supplied by the knowledge graph (0-1 range).
    downstream_nodes:
        Mapping of downstream node names to effective rate constants.
    stimulus:
        Global scaling factor capturing ligand stimulus strength.
    timepoints:
        Ordered sequence of simulation timepoints (hours).
    """

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
    summary: Dict[str, float]
    uncertainty: Dict[str, float]


def simulate_cascade(params: MolecularCascadeParams) -> MolecularCascadeResult:
    """Compute a smooth cascade response for the provided parameters.

    The placeholder implementation applies an exponential convergence to a
    receptor-weighted stimulus.  It preserves the deterministic structure of
    the real PySB model while keeping the dependency footprint minimal.
    """

    if len(params.timepoints) == 0:
        raise ValueError("timepoints must contain at least one value")

    time = np.asarray(params.timepoints, dtype=float)
    if np.any(np.diff(time) <= 0):
        raise ValueError("timepoints must be strictly increasing")

    # Aggregate receptor influence using knowledge-graph weights.  Mechanistic
    # evidence increases effective stimulus, reflecting higher confidence that
    # the receptor truly drives the pathway.
    receptor_effect = 0.0
    for name, occ in params.receptor_states.items():
        weight = params.receptor_weights.get(name, 0.5)
        evidence = params.receptor_evidence.get(name, 0.5)
        receptor_effect += occ * weight * (0.5 + 0.5 * evidence)
    receptor_effect *= params.stimulus

    if not params.downstream_nodes:
        raise ValueError("at least one downstream node must be supplied")

    node_activity: Dict[str, npt.NDArray[np.float64]] = {}
    for node, rate in params.downstream_nodes.items():
        rate = max(rate, 1e-3)
        response = receptor_effect * (1.0 - np.exp(-rate * (time - time[0])))
        node_activity[node] = response.astype(float, copy=False)

    stacked = np.vstack(list(node_activity.values()))
    mean_activity = stacked.mean(axis=0)

    transient_peak = float(np.max(mean_activity))
    steady_state = float(mean_activity[-1])
    auc = float(np.trapezoid(mean_activity, time))
    duration = float(time[-1] - time[0])
    activation_index = float(auc / duration) if duration > 0 else float(mean_activity[-1])

    evidence_values = list(params.receptor_evidence.values()) or [0.5]
    mean_evidence = float(np.clip(np.mean(evidence_values), 0.0, 1.0))
    uncertainty_level = float(max(0.05, 1.0 - mean_evidence))

    summary = {
        "transient_peak": transient_peak,
        "steady_state": steady_state,
        "activation_index": activation_index,
        "pathway": params.pathway,
    }
    uncertainty = {
        "cascade": uncertainty_level,
        "steady_state": float(max(0.05, 1.0 - mean_evidence * 0.9)),
    }

    return MolecularCascadeResult(
        timepoints=time,
        node_activity=node_activity,
        summary=summary,
        uncertainty=uncertainty,
    )
