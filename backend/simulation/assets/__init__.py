"""Reference assets bundled with the simulation package."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import numpy.typing as npt

__all__ = [
    "load_reference_pathway",
    "get_default_ospsuite_project_path",
    "load_reference_pbpk_curves",
    "load_reference_connectivity",
]


def _read_json_asset(name: str) -> Dict[str, Any]:
    package = resources.files(__name__)
    with resources.as_file(package.joinpath(name)) as asset_path:
        with asset_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def load_reference_pathway() -> Dict[str, Any]:
    """Return the bundled PySB pathway template."""

    try:
        data = _read_json_asset("pysb_reference_pathway.json")
    except FileNotFoundError:
        data = {
            "pathway": "monoamine_neurotrophin_cascade",
            "downstream_nodes": {"CREB": 0.18, "BDNF": 0.09, "mTOR": 0.05},
        }
    else:
        downstream = data.get("downstream_nodes", {})
        data["downstream_nodes"] = {str(key): float(value) for key, value in downstream.items()}
    return data


def get_default_ospsuite_project_path() -> str:
    """Return the file path for the packaged PK/PD reference project."""

    package = resources.files(__name__)
    with resources.as_file(package.joinpath("pbpk_reference_project.json")) as asset_path:
        return str(Path(asset_path))


def load_reference_pbpk_curves() -> Tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    Dict[str, npt.NDArray[np.float64]],
]:
    """Load precomputed concentration curves for the reference PBPK model."""

    data = _read_json_asset("pbpk_reference_project.json")
    time = np.asarray(data.get("time", []), dtype=float)
    plasma = np.asarray(data.get("plasma_concentration", []), dtype=float)
    brain = np.asarray(data.get("brain_concentration", []), dtype=float)
    region_data: Dict[str, npt.NDArray[np.float64]] = {}
    for region, values in (data.get("region_brain_concentration", {}) or {}).items():
        region_array = np.asarray(values, dtype=float)
        region_data[str(region)] = region_array
    return time, plasma, brain, region_data


def load_reference_connectivity() -> Tuple[List[str], npt.NDArray[np.float64]]:
    """Return the regional labels and connectivity weights for TVB integration."""

    data = _read_json_asset("tvb_reference_connectivity.json")
    regions = [str(label) for label in data.get("regions", [])]
    weights = np.asarray(data.get("weights", []), dtype=float)
    if weights.ndim != 2:
        weights = np.zeros((len(regions), len(regions)), dtype=float)
    return regions, weights
