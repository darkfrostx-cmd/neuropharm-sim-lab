"""Atlas overlay service exposing anatomical coordinates and volumes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..graph.ingest_atlases import AllenAtlasClient, EBrainsAtlasClient
from ..graph.models import Node
from ..graph.service import GraphService


ALLEN_ANNOTATION_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_10.nrrd"
)


@dataclass(slots=True)
class AtlasCoordinate:
    reference_space: int | None
    x_mm: float | None
    y_mm: float | None
    z_mm: float | None
    source: str


@dataclass(slots=True)
class AtlasVolume:
    name: str
    url: str
    format: str
    description: str | None = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class AtlasOverlay:
    node_id: str
    provider: str
    coordinates: List[AtlasCoordinate] = field(default_factory=list)
    volumes: List[AtlasVolume] = field(default_factory=list)


class AtlasOverlayService:
    """Resolve atlas overlays for graph nodes."""

    def __init__(
        self,
        graph_service: GraphService,
        *,
        allen_client: AllenAtlasClient | None = None,
        ebrains_client: EBrainsAtlasClient | None = None,
    ) -> None:
        self.graph_service = graph_service
        try:
            self._allen = allen_client or AllenAtlasClient()
        except Exception:
            self._allen = allen_client
        try:
            self._ebrains = ebrains_client or EBrainsAtlasClient()
        except Exception:
            self._ebrains = ebrains_client

    def lookup(self, node_id: str) -> AtlasOverlay:
        node = self.graph_service.store.get_node(node_id)
        if node is None:
            raise KeyError(node_id)
        provider = (node.provided_by or "").lower()
        if "allen" in provider or node.id.isdigit():
            return self._allen_overlay(node)
        if "ebrains" in provider or node.id.startswith("http"):
            return self._ebrains_overlay(node)
        return AtlasOverlay(node_id=node.id, provider=node.provided_by or "unknown")

    # ------------------------------------------------------------------
    # Provider-specific helpers
    # ------------------------------------------------------------------
    def _allen_overlay(self, node: Node) -> AtlasOverlay:
        coordinates = self._coerce_allen_centers(node)
        volumes = [
            AtlasVolume(
                name="Allen CCF annotation (10µm)",
                url=ALLEN_ANNOTATION_URL,
                format="nrrd",
                description="Allen Mouse Common Coordinate Framework segmentation volume",
                metadata={"resolution_um": 10, "type": "segmentation"},
            )
        ]
        return AtlasOverlay(node_id=node.id, provider=node.provided_by or "Allen Brain Atlas", coordinates=coordinates, volumes=volumes)

    def _coerce_allen_centers(self, node: Node) -> List[AtlasCoordinate]:
        centres_raw = node.attributes.get("centers") if isinstance(node.attributes, dict) else None
        if not centres_raw and self._allen is not None:
            try:
                centres_raw = self._allen.fetch_centers(int(node.id))
            except Exception:
                centres_raw = []
        coordinates: List[AtlasCoordinate] = []
        for entry in centres_raw or []:
            ref = entry.get("reference_space_id")
            x = entry.get("x")
            y = entry.get("y")
            z = entry.get("z")
            coordinates.append(
                AtlasCoordinate(
                    reference_space=int(ref) if isinstance(ref, (int, float)) else None,
                    x_mm=self._micron_to_mm(x),
                    y_mm=self._micron_to_mm(y),
                    z_mm=self._micron_to_mm(z),
                    source="allen",
                )
            )
        return coordinates

    def _ebrains_overlay(self, node: Node) -> AtlasOverlay:
        coordinates: List[AtlasCoordinate] = []
        coords_raw = node.attributes.get("coordinates") if isinstance(node.attributes, dict) else None
        if not coords_raw and self._ebrains is not None:
            try:
                coords_raw = next(
                    (region.get("hasCoordinates", []) for region in self._ebrains.iter_regions(limit=200) if region.get("@id") == node.id),
                    [],
                )
            except Exception:
                coords_raw = []
        region_urls: List[str] = []
        for entry in coords_raw or []:
            loc = entry.get("location") or {}
            coordinates.append(
                AtlasCoordinate(
                    reference_space=None,
                    x_mm=self._safe_float(loc.get("x")),
                    y_mm=self._safe_float(loc.get("y")),
                    z_mm=self._safe_float(loc.get("z")),
                    source="ebrains",
                )
            )
            ref_url = entry.get("@id")
            if isinstance(ref_url, str):
                region_urls.append(ref_url)
        volumes: List[AtlasVolume] = []
        if region_urls:
            volumes.append(
                AtlasVolume(
                    name="EBRAINS surface",
                    url=region_urls[0],
                    format="gltf",
                    metadata={"type": "surface"},
                )
            )
        return AtlasOverlay(node_id=node.id, provider=node.provided_by or "EBRAINS", coordinates=coordinates, volumes=volumes)

    @staticmethod
    def _micron_to_mm(value: object) -> Optional[float]:
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


__all__ = [
    "AtlasOverlay",
    "AtlasOverlayService",
    "AtlasCoordinate",
    "AtlasVolume",
]

