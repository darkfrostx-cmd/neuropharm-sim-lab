"""Static atlas reference assets used for offline ingestion and QA."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict


def _load_json(resource_name: str) -> Dict[str, Any]:
    with resources.files(__package__).joinpath(resource_name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_hcp_reference() -> Dict[str, Any]:
    """Return curated Human Connectome Project atlas metadata."""

    return _load_json("hcp_atlas_sample.json")


def load_julich_reference() -> Dict[str, Any]:
    """Return curated Julich-Brain atlas metadata."""

    return _load_json("julich_atlas_sample.json")


__all__ = [
    "load_hcp_reference",
    "load_julich_reference",
]

