"""Allen Brain Atlas and EBRAINS ingestion."""

from __future__ import annotations

from typing import Iterable, Iterator

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .ingest_base import BaseIngestionJob
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node


class AllenAtlasClient:
    BASE_URL = "https://api.brain-map.org/api/v2/data/Structure/query.json"

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
        node = Node(
            id=record.get("id", "AllenStructure"),
            name=record.get("name", "Structure"),
            category=BiolinkEntity.BRAIN_REGION,
            provided_by=self.source,
            attributes={"acronym": record.get("acronym")},
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
            attributes={"atlas": record.get("atlas")},
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


__all__ = [
    "AllenAtlasClient",
    "EBrainsAtlasClient",
    "AllenAtlasIngestion",
    "EBrainsAtlasIngestion",
]
