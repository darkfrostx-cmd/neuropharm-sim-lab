"""Allen Brain Atlas and EBRAINS ingestion."""

from __future__ import annotations

from typing import Iterable, Iterator

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from ..atlas.assets import load_hcp_reference, load_julich_reference
from .ingest_base import BaseIngestionJob
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node


class AllenAtlasClient:
    BASE_URL = "https://api.brain-map.org/api/v2/data/Structure/query.json"
    CENTER_URL = "https://api.brain-map.org/api/v2/data/StructureCenter/query.json"

    def __init__(self, session: "requests.Session" | None = None) -> None:
        if requests is None:
            raise ImportError("requests is required for AllenAtlasClient")
        self.session = session or requests.Session()

    def iter_structures(self, limit: int = 100) -> Iterator[dict]:
        params = {"criteria": "[graph_id$eq1]", "num_rows": limit}
        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        structures = response.json().get("msg", [])
        return iter(structures)

    def fetch_centers(self, structure_id: int) -> list[dict]:
        params = {"criteria": f"[structure_id$eq{structure_id}]"}
        response = self.session.get(self.CENTER_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json().get("msg", []) or []


class EBrainsAtlasClient:
    BASE_URL = "https://ebrains-curation.eu/api/atlases/regions"

    def __init__(self, session: "requests.Session" | None = None) -> None:
        if requests is None:
            raise ImportError("requests is required for EBrainsAtlasClient")
        self.session = session or requests.Session()

    def iter_regions(self, limit: int = 100) -> Iterator[dict]:
        response = self.session.get(self.BASE_URL, timeout=30)
        response.raise_for_status()
        results = response.json().get("results", [])
        return iter(results[:limit])


class AllenAtlasIngestion(BaseIngestionJob):
    name = "allen_atlas"
    source = "Allen Brain Atlas"

    def __init__(self, client: AllenAtlasClient | None = None) -> None:
        self.client = client or AllenAtlasClient()

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        iterator = self.client.iter_structures(limit=limit or 100)
        if limit is None:
            return iterator
        return (record for i, record in enumerate(iterator) if i < limit)

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        structure_id = int(record.get("id", 0) or 0)
        node_id = record.get("id", "AllenStructure")
        attributes: dict[str, object] = {"acronym": record.get("acronym")}
        if structure_id:
            try:
                centers = [
                    {
                        "reference_space_id": center.get("reference_space_id"),
                        "x": center.get("x"),
                        "y": center.get("y"),
                        "z": center.get("z"),
                    }
                    for center in self.client.fetch_centers(structure_id)
                ]
            except Exception:
                centers = []
            if centers:
                attributes["centers"] = centers
        node = Node(
            id=node_id,
            name=record.get("name", "Structure"),
            category=BiolinkEntity.BRAIN_REGION,
            provided_by=self.source,
            attributes=attributes,
        )
        parent_id = record.get("parent_structure_id")
        edges: list[Edge] = []
        if parent_id:
            edges.append(
                Edge(
                    subject=node.id,
                    predicate=BiolinkPredicate.PART_OF,
                    object=str(parent_id),
                    evidence=[self.make_evidence(self.source, None, None, relation="hierarchy")],
                )
            )
        return [node], edges


class EBrainsAtlasIngestion(BaseIngestionJob):
    name = "ebrains_atlas"
    source = "EBRAINS"

    def __init__(self, client: EBrainsAtlasClient | None = None) -> None:
        self.client = client or EBrainsAtlasClient()

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        iterator = self.client.iter_regions(limit=limit or 100)
        if limit is None:
            return iterator
        return (record for i, record in enumerate(iterator) if i < limit)

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        node = Node(
            id=record.get("@id", record.get("identifier", "EBRAINSRegion")),
            name=record.get("name", "Region"),
            category=BiolinkEntity.BRAIN_REGION,
            provided_by=self.source,
            attributes={
                "atlas": record.get("atlas"),
                "coordinates": record.get("hasCoordinates", []),
            },
        )
        coordinates = record.get("hasCoordinates", [])
        edges: list[Edge] = []
        for coord in coordinates:
            edges.append(
                Edge(
                    subject=node.id,
                    predicate=BiolinkPredicate.LOCATED_IN,
                    object=coord.get("space", "space"),
                    evidence=[self.make_evidence(self.source, coord.get("@id"), None, type=coord.get("type", "coordinate"))],
                )
            )
        return [node], edges


class HCPAtlasIngestion(BaseIngestionJob):
    name = "hcp_atlas"
    source = "Human Connectome Project"

    def __init__(self, reference: dict | None = None) -> None:
        self._reference = reference or load_hcp_reference()

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        regions = list(self._reference.get("regions", []))
        if limit is not None:
            return regions[: limit or 0]
        return regions

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        node = Node(
            id=record.get("id", "HCPRegion"),
            name=record.get("name", "HCP region"),
            category=BiolinkEntity.BRAIN_REGION,
            provided_by=self.source,
            attributes={
                "space": record.get("space"),
                "coordinates": record.get("coordinates", []),
                "volumes": record.get("volumes", []),
                "surfaces": record.get("surfaces", []),
            },
        )
        edges: list[Edge] = []
        for volume in record.get("volumes", []):
            evidence = self.make_evidence(self.source, volume.get("url"), None, type=volume.get("format"))
            edges.append(
                Edge(
                    subject=node.id,
                    predicate=BiolinkPredicate.HAS_PART,
                    object=volume.get("name", "HCP volume"),
                    evidence=[evidence],
                )
            )
        space = record.get("space")
        if space:
            edges.append(
                Edge(
                    subject=node.id,
                    predicate=BiolinkPredicate.LOCATED_IN,
                    object=str(space),
                    evidence=[self.make_evidence(self.source, None, None, type="space")],
                )
            )
        return [node], edges


class JulichAtlasIngestion(BaseIngestionJob):
    name = "julich_atlas"
    source = "Julich-Brain"

    def __init__(self, reference: dict | None = None) -> None:
        self._reference = reference or load_julich_reference()

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        regions = list(self._reference.get("regions", []))
        if limit is not None:
            return regions[: limit or 0]
        return regions

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        node = Node(
            id=record.get("id", "JulichRegion"),
            name=record.get("name", "Julich region"),
            category=BiolinkEntity.BRAIN_REGION,
            provided_by=self.source,
            attributes={
                "space": record.get("space"),
                "coordinates": record.get("coordinates", []),
                "volumes": record.get("volumes", []),
                "surfaces": record.get("surfaces", []),
            },
        )
        edges: list[Edge] = []
        for surface in record.get("surfaces", []):
            evidence = self.make_evidence(self.source, surface.get("url"), None, type=surface.get("format"))
            edges.append(
                Edge(
                    subject=node.id,
                    predicate=BiolinkPredicate.HAS_PART,
                    object=surface.get("name", "Julich surface"),
                    evidence=[evidence],
                )
            )
        space = record.get("space")
        if space:
            edges.append(
                Edge(
                    subject=node.id,
                    predicate=BiolinkPredicate.LOCATED_IN,
                    object=str(space),
                    evidence=[self.make_evidence(self.source, None, None, type="space")],
                )
            )
        return [node], edges


__all__ = [
    "AllenAtlasClient",
    "EBrainsAtlasClient",
    "AllenAtlasIngestion",
    "EBrainsAtlasIngestion",
    "HCPAtlasIngestion",
    "JulichAtlasIngestion",
]
