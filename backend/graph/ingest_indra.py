"""INDRA ingestion job."""

from __future__ import annotations

from typing import Iterable, Iterator

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .ingest_base import BaseIngestionJob
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node


class IndraClient:
    BASE_URL = "https://db.indra.bio/statements/from_agents"

    def __init__(self, session: "requests.Session" | None = None) -> None:
        if requests is None:
            raise ImportError("requests is required for IndraClient")
        self.session = session or requests.Session()

    def iter_statements(self, agent: str, limit: int = 100) -> Iterator[dict]:
        params = {"agents": agent, "format": "json", "size": limit}
        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return iter(data.get("statements", []))


class IndraIngestion(BaseIngestionJob):
    name = "indra"
    source = "INDRA"

    def __init__(self, client: IndraClient | None = None, agent: str = "5-HT2A") -> None:
        self.client = client or IndraClient()
        self.agent = agent

    def fetch(self, limit: int | None = None) -> Iterable[dict]:
        iterator = self.client.iter_statements(self.agent, limit=limit or 100)
        if limit is None:
            return iterator
        return (record for i, record in enumerate(iterator) if i < limit)

    def transform(self, record: dict) -> tuple[list[Node], list[Edge]]:
        nodes: list[Node] = []
        edges: list[Edge] = []
        subj = record.get("subject") or {}
        obj = record.get("object") or {}
        evidence = record.get("evidence", [])
        if not subj or not obj:
            return nodes, edges
        subject_node = Node(
            id=subj.get("db_refs", {}).get("HGNC") or subj.get("name", "subject"),
            name=subj.get("name", "subject"),
            category=BiolinkEntity.GENE,
            provided_by=self.source,
        )
        object_node = Node(
            id=obj.get("db_refs", {}).get("HGNC") or obj.get("name", "object"),
            name=obj.get("name", "object"),
            category=BiolinkEntity.GENE,
            provided_by=self.source,
        )
        nodes.extend([subject_node, object_node])
        publications: list[str] = []
        edge_evidence = []
        for ev in evidence:
            pub = ev.get("pmid") or ev.get("text_refs", {}).get("PMID")
            if pub:
                publications.append(pub)
            belief_str = ev.get("annotations", {}).get("belief") if ev.get("annotations") else None
            confidence = float(belief_str) if belief_str else None
            edge_evidence.append(
                self.make_evidence(
                    self.source,
                    pub,
                    confidence,
                    statement=record.get("type"),
                )
            )
        edges.append(
            Edge(
                subject=subject_node.id,
                predicate=BiolinkPredicate.AFFECTS,
                object=object_node.id,
                confidence=record.get("belief"),
                publications=publications,
                evidence=edge_evidence,
            )
        )
        return nodes, edges


__all__ = ["IndraClient", "IndraIngestion"]
