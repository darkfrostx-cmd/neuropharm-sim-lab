"""Atlas overlay service exposing anatomical coordinates and volumes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Set

from ..graph.ingest_atlases import AllenAtlasClient, EBrainsAtlasClient
from ..graph.models import Node
from ..graph.service import GraphService
from .assets import load_hcp_reference, load_julich_reference


ALLEN_ANNOTATION_URL = (
    "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_10.nrrd"
)


def _make_keys(*aliases: str) -> Set[str]:
    return {alias.lower() for alias in aliases if alias}


_CURATED_LIBRARY: List[Dict[str, object]] = [
    {
        "provider": "Harvard-Oxford",
        "keys": _make_keys("UBERON:0002421", "hippocampus", "hippocampal formation"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -23.8, "y_mm": -18.6, "z_mm": -15.4},
            {"reference_space_id": 997, "x_mm": 23.4, "y_mm": -18.3, "z_mm": -15.2},
        ],
        "volumes": [
            {
                "name": "Harvard-Oxford hippocampus mask",
                "url": "https://neurovault.org/media/images/2624/hippocampus_mask.nii.gz",
                "format": "nii.gz",
                "metadata": {"space": "MNI152", "type": "mask"},
            }
        ],
    },
    {
        "provider": "Harvard-Oxford",
        "keys": _make_keys("UBERON:0001950", "medial prefrontal cortex", "mPFC", "prefrontal medial"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -6.0, "y_mm": 46.5, "z_mm": -2.5},
            {"reference_space_id": 997, "x_mm": 6.2, "y_mm": 46.3, "z_mm": -2.1},
        ],
        "volumes": [
            {
                "name": "Harvard-Oxford frontal medial cortex",
                "url": "https://neurovault.org/media/images/2624/frontal_medial.nii.gz",
                "format": "nii.gz",
                "metadata": {"space": "MNI152", "type": "mask"},
            }
        ],
    },
    {
        "provider": "NeuroVault",
        "keys": _make_keys("UBERON:0001881", "ventral tegmental area", "VTA"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -4.5, "y_mm": -13.8, "z_mm": -10.5},
            {"reference_space_id": 997, "x_mm": 4.2, "y_mm": -13.6, "z_mm": -10.2},
        ],
        "volumes": [
            {
                "name": "Probabilistic VTA mask",
                "url": "https://neurovault.org/media/images/4337/prob_vta.nii.gz",
                "format": "nii.gz",
                "metadata": {"space": "MNI152", "type": "probability"},
            }
        ],
    },
    {
        "provider": "NeuroVault",
        "keys": _make_keys("UBERON:0006102", "nucleus accumbens", "ventral striatum", "NAc"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -10.2, "y_mm": 10.4, "z_mm": -7.8},
            {"reference_space_id": 997, "x_mm": 10.5, "y_mm": 10.1, "z_mm": -7.6},
        ],
        "volumes": [
            {
                "name": "Oxford-GSK-Imanova striatum atlas",
                "url": "https://neurovault.org/media/images/2445/oxford_gsk_imanova_striatum_mask.nii.gz",
                "format": "nii.gz",
                "metadata": {"space": "MNI152", "type": "mask"},
            }
        ],
    },
    {
        "provider": "Harvard-Oxford",
        "keys": _make_keys("UBERON:0001882", "amygdala"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -22.6, "y_mm": -4.5, "z_mm": -15.8},
            {"reference_space_id": 997, "x_mm": 22.9, "y_mm": -4.3, "z_mm": -15.6},
        ],
        "volumes": [
            {
                "name": "Harvard-Oxford amygdala mask",
                "url": "https://neurovault.org/media/images/2624/amygdala_mask.nii.gz",
                "format": "nii.gz",
                "metadata": {"space": "MNI152", "type": "mask"},
            }
        ],
    },
    {
        "provider": "Harvard-Oxford",
        "keys": _make_keys("UBERON:0001870", "insula", "insular cortex"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -34.5, "y_mm": 14.6, "z_mm": 2.2},
            {"reference_space_id": 997, "x_mm": 34.7, "y_mm": 14.5, "z_mm": 2.5},
        ],
        "volumes": [
            {
                "name": "Harvard-Oxford insular cortex mask",
                "url": "https://neurovault.org/media/images/2624/insula_mask.nii.gz",
                "format": "nii.gz",
                "metadata": {"space": "MNI152", "type": "mask"},
            }
        ],
    },
    {
        "provider": "Allen+NeuroMorph",
        "keys": _make_keys("UBERON:0001898", "locus coeruleus"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -1.8, "y_mm": -34.5, "z_mm": -18.2},
            {"reference_space_id": 997, "x_mm": 1.7, "y_mm": -34.6, "z_mm": -18.0},
        ],
        "volumes": [
            {
                "name": "LC probabilistic atlas",
                "url": "https://neurovault.org/media/images/3915/lc_probabilistic.nii.gz",
                "format": "nii.gz",
                "metadata": {"space": "MNI152", "type": "probability"},
            }
        ],
    },
    {
        "provider": "EBRAINS",
        "keys": _make_keys("UBERON:0002303", "anterior cingulate cortex", "ACC"),
        "coordinates": [
            {"reference_space_id": 997, "x_mm": -5.0, "y_mm": 39.0, "z_mm": 20.5},
            {"reference_space_id": 997, "x_mm": 5.3, "y_mm": 38.7, "z_mm": 20.2},
        ],
        "volumes": [
            {
                "name": "EBRAINS ACC surface",
                "url": "https://ebrains.eu/repository/atlas/acc_surface.gltf",
                "format": "gltf",
                "metadata": {"type": "surface", "space": "ICBM152"},
            }
        ],
    },
]


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
        hcp_reference: dict | None = None,
        julich_reference: dict | None = None,
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
        self._hcp_reference = hcp_reference or load_hcp_reference()
        self._julich_reference = julich_reference or load_julich_reference()

    def lookup(self, node_id: str) -> AtlasOverlay:
        node = self.graph_service.store.get_node(node_id)
        if node is None:
            raise KeyError(node_id)
        provider = (node.provided_by or "").lower()
        curated = self._curated_overlay(node)
        if curated is not None:
            return curated
        if self._hcp_reference:
            if "hcp" in provider or "connectome" in provider:
                matched = self._reference_overlay(node, self._hcp_reference, "Human Connectome Project")
                if matched:
                    return matched
        if self._julich_reference:
            if "julich" in provider:
                matched = self._reference_overlay(node, self._julich_reference, "Julich-Brain")
                if matched:
                    return matched
        if "allen" in provider or node.id.isdigit():
            return self._allen_overlay(node)
        if "ebrains" in provider or node.id.startswith("http"):
            return self._ebrains_overlay(node)
        if self._hcp_reference:
            matched = self._reference_overlay(node, self._hcp_reference, "Human Connectome Project")
            if matched:
                return matched
        if self._julich_reference:
            matched = self._reference_overlay(node, self._julich_reference, "Julich-Brain")
            if matched:
                return matched
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

    def _curated_overlay(self, node: Node) -> AtlasOverlay | None:
        lookup_keys: Set[str] = {node.id.lower(), (node.name or "").lower()}
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        synonyms = attributes.get("synonyms") if isinstance(attributes, dict) else None
        if isinstance(synonyms, Iterable) and not isinstance(synonyms, (str, bytes)):
            lookup_keys.update(str(value).lower() for value in synonyms if isinstance(value, str))
        if isinstance(attributes, dict):
            for key in ("uberon_id", "atlas_id", "curie"):
                raw = attributes.get(key)
                if isinstance(raw, str):
                    lookup_keys.add(raw.lower())
        lookup_keys = {key for key in lookup_keys if key}
        for entry in _CURATED_LIBRARY:
            keys: Set[str] = entry["keys"]  # type: ignore[assignment]
            if lookup_keys & keys:
                coordinates = [
                    AtlasCoordinate(
                        reference_space=coord.get("reference_space_id"),
                        x_mm=coord.get("x_mm"),
                        y_mm=coord.get("y_mm"),
                        z_mm=coord.get("z_mm"),
                        source="curated",
                    )
                    for coord in entry["coordinates"]  # type: ignore[index]
                ]
                volumes = [
                    AtlasVolume(
                        name=volume["name"],
                        url=volume["url"],
                        format=volume["format"],
                        description=volume.get("description"),
                        metadata=volume.get("metadata", {}),
                    )
                    for volume in entry["volumes"]  # type: ignore[index]
                ]
                return AtlasOverlay(
                    node_id=node.id,
                    provider=str(entry.get("provider", "curated")),
                    coordinates=coordinates,
                    volumes=volumes,
                )
        return None

    def _reference_overlay(
        self,
        node: Node,
        reference: Mapping[str, object] | None,
        provider_name: str,
    ) -> AtlasOverlay | None:
        if not reference:
            return None
        lookup_keys: Set[str] = {node.id.lower(), (node.name or "").lower()}
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        synonyms = attributes.get("synonyms") if isinstance(attributes, dict) else None
        if isinstance(synonyms, Iterable) and not isinstance(synonyms, (str, bytes)):
            lookup_keys.update(str(value).lower() for value in synonyms if isinstance(value, str))
        lookup_keys = {key for key in lookup_keys if key}
        for region in reference.get("regions", []):
            region_id = str(region.get("id", "")).lower()
            region_name = str(region.get("name", "")).lower()
            region_keys = {region_id, region_name}
            for alias in region.get("aliases", []):
                region_keys.add(str(alias).lower())
            if lookup_keys & region_keys:
                coordinates = [
                    AtlasCoordinate(
                        reference_space=coord.get("reference_space_id"),
                        x_mm=coord.get("x_mm"),
                        y_mm=coord.get("y_mm"),
                        z_mm=coord.get("z_mm"),
                        source=provider_name.lower(),
                    )
                    for coord in region.get("coordinates", [])
                ]
                volumes = [
                    AtlasVolume(
                        name=volume.get("name", "atlas volume"),
                        url=volume.get("url", ""),
                        format=volume.get("format", ""),
                        description=volume.get("description"),
                        metadata=volume.get("metadata", {}),
                    )
                    for volume in region.get("volumes", [])
                ]
                for surface in region.get("surfaces", []):
                    metadata = dict(surface.get("metadata", {}))
                    metadata.setdefault("type", "surface")
                    volumes.append(
                        AtlasVolume(
                            name=surface.get("name", "atlas surface"),
                            url=surface.get("url", ""),
                            format=surface.get("format", ""),
                            metadata=metadata,
                        )
                    )
                return AtlasOverlay(node_id=node.id, provider=provider_name, coordinates=coordinates, volumes=volumes)
        return None

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

