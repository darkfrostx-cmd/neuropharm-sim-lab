"""INDRA ingestion job."""

from __future__ import annotations

from typing import Iterable, Iterator, Mapping

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .evidence_quality import (
    normalise_chronicity_label,
    normalise_design_label,
    normalise_species_label,
)
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
            metadata = self._extract_metadata(ev)
            edge_evidence.append(
                self.make_evidence(
                    self.source,
                    pub,
                    confidence,
                    statement=record.get("type"),
                    **{key: value for key, value in metadata.items() if value},
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

    @staticmethod
    def _extract_metadata(evidence: Mapping[str, object]) -> dict[str, str | None]:
        annotations = evidence.get("annotations") if isinstance(evidence.get("annotations"), Mapping) else {}
        context = evidence.get("context") if isinstance(evidence.get("context"), Mapping) else {}

        species_candidate = None
        for key in ("species", "subject_species", "object_species"):
            value = annotations.get(key) if isinstance(annotations, Mapping) else None
            if value:
                species_candidate = value
                break
        if not species_candidate:
            species_candidate = context.get("species") if isinstance(context, Mapping) else None
        species = normalise_species_label(str(species_candidate)) if species_candidate else None

        chronicity_candidate = None
        for key in ("chronicity", "timecourse", "treatment"):
            value = annotations.get(key) if isinstance(annotations, Mapping) else None
            if value:
                chronicity_candidate = value
                break
        chronicity = normalise_chronicity_label(str(chronicity_candidate)) if chronicity_candidate else None

        design_candidate = None
        for key in ("design", "experiment_type", "assay", "evidence_type"):
            value = annotations.get(key) if isinstance(annotations, Mapping) else None
            if value:
                design_candidate = value
                break
        if not design_candidate and isinstance(context, Mapping):
            design_candidate = context.get("setting")
        design = normalise_design_label(str(design_candidate)) if design_candidate else None

        return {"species": species, "chronicity": chronicity, "design": design}


__all__ = ["IndraClient", "IndraIngestion"]
