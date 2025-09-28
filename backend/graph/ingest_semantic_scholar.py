"""Ingestion job for Semantic Scholar literature records."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Sequence

from .entity_grounding import GroundingResolver
from .ingest_base import BaseIngestionJob
from .literature import LiteratureRecord, SemanticScholarClient
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node

LOGGER = logging.getLogger(__name__)


_DEFAULT_QUERIES: Sequence[str] = (
    "serotonin transporter SLC6A4 cortical plasticity",
    "BDNF synaptic potentiation antidepressant",
    "alpha2A adrenergic HCN prefrontal attention",
    "gut brain axis microbiome dopamine",
    "TrkB facilitation chronic stress",
    "HCN channel locus coeruleus neuromodulation",
)


@dataclass(slots=True)
class _QueryBatch:
    query: str
    records: Sequence[LiteratureRecord]


class SemanticScholarIngestion(BaseIngestionJob):
    """Hydrate the knowledge graph with Semantic Scholar publications."""

    name = "semantic_scholar"
    source = "Semantic Scholar"

    def __init__(
        self,
        *,
        client: SemanticScholarClient | None = None,
        queries: Sequence[str] | None = None,
        grounder: GroundingResolver | None = None,
    ) -> None:
        self.client = client or SemanticScholarClient()
        self.queries = tuple(queries) if queries is not None else _DEFAULT_QUERIES
        if not self.queries:
            raise ValueError("SemanticScholarIngestion requires at least one query term")
        self.grounder = grounder or GroundingResolver()

    # ------------------------------------------------------------------
    # BaseIngestionJob API
    # ------------------------------------------------------------------
    def fetch(self, limit: int | None = None) -> Iterable[_QueryBatch]:
        per_query = self._per_query_limit(limit)
        for query in self.queries:
            try:
                records = list(self.client.search(query, limit=per_query))
            except Exception as exc:  # pragma: no cover - network failure
                LOGGER.warning("Semantic Scholar request failed for '%s': %s", query, exc)
                continue
            if not records:
                LOGGER.debug("Semantic Scholar query '%s' yielded no records", query)
                continue
            yield _QueryBatch(query=query, records=records)

    def transform(self, batch: Mapping[str, object]) -> tuple[List[Node], List[Edge]]:
        if not isinstance(batch, _QueryBatch):
            batch = _QueryBatch(query=str(batch.get("query")), records=batch.get("records", []))  # type: ignore[arg-type]
        nodes: dict[str, Node] = {}
        edges: List[Edge] = []
        query_terms = self._derive_focus_terms(batch.query)
        for record in batch.records:
            publication_node = self._publication_node(record)
            if publication_node.id not in nodes:
                nodes[publication_node.id] = publication_node
            for term in query_terms:
                grounded = self.grounder.resolve(term)
                grounded_node = self._grounded_node(grounded)
                if grounded_node.id not in nodes:
                    nodes[grounded_node.id] = grounded_node
                edge = self._link_node(grounded_node, publication_node, record, batch.query)
                edges.append(edge)
        return list(nodes.values()), edges

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _per_query_limit(self, limit: int | None) -> int:
        if limit is None or limit <= 0:
            return 10
        return max(1, math.ceil(limit / len(self.queries)))

    def _derive_focus_terms(self, query: str) -> Sequence[str]:
        tokens = [token.strip() for token in query.split() if token.strip()]
        if len(tokens) <= 3:
            return tokens
        # retain informative bi-grams by sliding window
        focus: List[str] = []
        for i in range(len(tokens) - 1):
            pair = " ".join(tokens[i : i + 2])
            if tokens[i].lower() in {"the", "and", "of", "in"}:
                continue
            focus.append(pair)
        # ensure singletons for trailing tokens
        focus.extend(tokens[-2:])
        return tuple(dict.fromkeys(focus))

    def _publication_node(self, record: LiteratureRecord) -> Node:
        identifier = record.identifier or f"SEM:{abs(hash(record.title))}"  # deterministic fallback
        attributes = {
            "score": record.score,
            "snippet": record.snippet,
            "source": record.source,
        }
        if record.year is not None:
            attributes["year"] = record.year
        return Node(
            id=str(identifier),
            name=record.title,
            category=BiolinkEntity.PUBLICATION,
            provided_by=self.source,
            attributes=attributes,
        )

    def _grounded_node(self, grounded) -> Node:
        return Node(
            id=grounded.id,
            name=grounded.name,
            category=grounded.category,
            provided_by="GroundingResolver",
            synonyms=list(grounded.synonyms),
            xrefs=list(grounded.xrefs),
            attributes={
                "grounding_confidence": grounded.confidence,
                "grounding_strategy": grounded.provenance.get("strategy") if grounded.provenance else None,
            },
        )

    def _link_node(self, source: Node, publication: Node, record: LiteratureRecord, query: str) -> Edge:
        confidence = float(max(0.25, min(0.95, 0.45 + 0.02 * math.log1p(record.score or 0.0))))
        evidence = self.make_evidence(
            self.source,
            publication.id if publication.id else record.identifier,
            confidence,
            snippet=record.snippet,
            year=record.year,
            url=record.url,
        )
        evidence.annotations["source_query"] = query
        if record.url:
            evidence.annotations["url"] = record.url
        if record.snippet:
            evidence.annotations["snippet"] = record.snippet
        return Edge(
            subject=source.id,
            predicate=BiolinkPredicate.RELATED_TO,
            object=publication.id,
            relation="biolink:related_to",
            confidence=confidence,
            publications=[publication.id] if publication.id else [],
            evidence=[evidence],
            qualifiers={
                "query": source.name,
                "source_query": query,
                "source_score": record.score,
            },
        )


__all__ = ["SemanticScholarIngestion"]
