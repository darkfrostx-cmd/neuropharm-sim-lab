"""Geometry QA harness for atlas overlays."""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping

from . import AtlasOverlay


def validate_overlay_geometry(overlay: AtlasOverlay) -> List[str]:
    """Return a list of validation issues for ``overlay``."""

    issues: List[str] = []
    if not overlay.coordinates:
        issues.append("missing_coordinates")
    else:
        for index, coord in enumerate(overlay.coordinates):
            if coord.x_mm is None or coord.y_mm is None or coord.z_mm is None:
                issues.append(f"coordinate_{index}_incomplete")
                continue
            if not (-120.0 <= coord.x_mm <= 120.0 and -120.0 <= coord.y_mm <= 120.0 and -120.0 <= coord.z_mm <= 120.0):
                issues.append(f"coordinate_{index}_out_of_bounds")

    if not overlay.volumes:
        issues.append("missing_volumes")
    else:
        for volume in overlay.volumes:
            if not volume.url:
                issues.append(f"volume_missing_url:{volume.name}")
            metadata = volume.metadata or {}
            if "type" not in metadata:
                issues.append(f"volume_missing_type:{volume.name}")
    return issues


def run_geometry_qa(overlays: Iterable[AtlasOverlay]) -> Mapping[str, List[str]]:
    """Validate ``overlays`` and return a mapping of node identifiers to issues."""

    results: Dict[str, List[str]] = {}
    for overlay in overlays:
        issues = validate_overlay_geometry(overlay)
        if issues:
            results[overlay.node_id] = issues
    return results


__all__ = [
    "validate_overlay_geometry",
    "run_geometry_qa",
]

