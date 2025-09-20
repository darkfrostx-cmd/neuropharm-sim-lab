"""OpenAlex ingestion job."""

from __future__ import annotations

from typing import Iterable, Iterator

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .ingest_base import BaseIngestionJob
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node


class OpenAlexClient:
    """Thin wrapper around the OpenAlex API.

    The client is intentionally minimal so it can be replaced with a stub in
    unit tests.  When running against the live service it honours the
    recommended polite usage guidelines (per-page limits, user agent headers).
    """

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, session: "requests.Session" | None = None, mailto: str | None = None) -> None:
        if requests is None:
            raise ImportError("requests is required for OpenAlexClient")
        self.session = session or requests.Session()
        self.mailto = mailto

    def iter_works(self, concept: str | None = None, search: str | None = None, per_page: int = 25) -> Iterator[dict]:
        cursor = "*"
        headers = {"User-Agent": "neuropharm-sim-lab/ingest"}
        params = {"per-page": per_page}
        if self.mailto:
            params["mailto"] = self.mailto
        if concept:
            params["filter"] = f"concepts.id:{concept}"
        if search:
            params["search"] = search
        while True:
            params["cursor"] = cursor
            response = self.session.get(self.BASE_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            payload = response.json()
            for record in payload.get("results", []):
                yield record
            cursor = payload.get("meta", {}).get("next_cursor")
            if not cursor:
                break


class OpenAlexIngestion(BaseIngestionJob):
    name = "openalex"
    source = "OpenAlex"

    def __init__(self, client: OpenAlexClient | None = None, concept: str | None = None, search: str | None = None) -> None:
        self.client = client or OpenAlexClient()
        self.concept = concept
        self.search = search

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        iterator = self.client.iter_works(concept=self.concept, search=self.search)
        if limit is None:
            return iterator

        def limited() -> Iterator[dict]:
            for i, record in enumerate(iterator):
                if i >= limit:
                    break
                yield record

        return limited()

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        nodes: list[Node] = []
        edges: list[Edge] = []
        work_id = record.get("id") or record.get("ids", {}).get("openalex")
        if not work_id:
            return nodes, edges
        work_node = Node(
            id=work_id,
            name=record.get("display_name", "Unknown work"),
            category=BiolinkEntity.PUBLICATION,
            provided_by=self.source,
            attributes={
                "publication_year": record.get("publication_year"),
                "cited_by_count": record.get("cited_by_count"),
            },
        )
        nodes.append(work_node)
        for authorship in record.get("authorships", []):
            author = authorship.get("author", {})
            author_id = author.get("orcid") or author.get("id")
            if not author_id:
                continue
            author_node = Node(
                id=author_id,
                name=author.get("display_name", "Unknown author"),
                category=BiolinkEntity.PERSON,
                provided_by=self.source,
            )
            nodes.append(author_node)
            edges.append(
                Edge(
                    subject=author_node.id,
                    predicate=BiolinkPredicate.CONTRIBUTES_TO,
                    object=work_node.id,
                    confidence=None,
                    evidence=[self.make_evidence(self.source, record.get("doi"), None, role=authorship.get("author_position", ""))],
                )
            )
        for concept in record.get("concepts", []):
            concept_id = concept.get("id") or concept.get("wikidata")
            if not concept_id:
                continue
            concept_node = Node(
                id=concept_id,
                name=concept.get("display_name", "Concept"),
                category=BiolinkEntity.NAMED_THING,
                provided_by=self.source,
            )
            nodes.append(concept_node)
            edges.append(
                Edge(
                    subject=work_node.id,
                    predicate=BiolinkPredicate.ASSOCIATED_WITH,
                    object=concept_node.id,
                    confidence=None,
                    evidence=[self.make_evidence(self.source, record.get("doi"), None, score=str(concept.get("score", "")))],
                )
            )
        return nodes, edges


__all__ = ["OpenAlexClient", "OpenAlexIngestion"]
