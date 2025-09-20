"""Common utilities for ingestion jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Protocol

from .models import Edge, Evidence, Node
from .persistence import GraphStore


class SupportsFetch(Protocol):  # pragma: no cover - structural typing helper
    def __iter__(self) -> Iterable[dict]:
        ...


@dataclass(slots=True)
class IngestionReport:
    """Simple summary returned after an ingestion run."""

    name: str
    records_processed: int = 0
    nodes_created: int = 0
    edges_created: int = 0


class BaseIngestionJob:
    """Base class implementing the ingestion workflow."""

    name: str = "base"
    source: str = ""

    def fetch(self, limit: int | None = None) -> Iterable[dict]:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def transform(self, record: dict) -> tuple[List[Node], List[Edge]]:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def run(self, store: GraphStore, limit: int | None = None) -> IngestionReport:
        report = IngestionReport(name=self.name)
        for i, record in enumerate(self.fetch(limit=limit)):
            nodes, edges = self.transform(record)
            store.upsert_nodes(nodes)
            store.upsert_edges(edges)
            report.records_processed += 1
            report.nodes_created += len(nodes)
            report.edges_created += len(edges)
            if limit is not None and i + 1 >= limit:
                break
        return report

    @staticmethod
    def make_evidence(source: str, reference: str | None, confidence: float | None, **annotations: str) -> Evidence:
        return Evidence(source=source, reference=reference, confidence=confidence, annotations=annotations)
