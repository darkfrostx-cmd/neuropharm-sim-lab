"""Utilities to bootstrap the knowledge graph with evidence sources."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator as TypingIterator, List, Mapping

from .ingest_base import BaseIngestionJob, IngestionReport
from .ingest_atlases import AllenAtlasIngestion, EBrainsAtlasIngestion
from .ingest_chembl import BindingDBIngestion, ChEMBLIngestion, IUPHARIngestion
from .ingest_pdsp import PDSPKiIngestion
from .ingest_indra import IndraIngestion
from .ingest_openalex import OpenAlexIngestion
from .ingest_semantic_scholar import SemanticScholarIngestion
from .models import BiolinkEntity, BiolinkPredicate, Edge, Evidence, Node
from .persistence import GraphStore, InMemoryGraphStore
from .service import GraphService

try:  # pragma: no cover - optional dependency
    from opentelemetry import trace
except Exception:  # pragma: no cover - optional dependency
    trace = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

DEFAULT_SEED_PATH = Path(__file__).with_suffix("").with_name("data") / "seed_graph.json"
_TRACER = trace.get_tracer(__name__) if trace is not None else None


@contextmanager
def _telemetry_span(name: str, attributes: Mapping[str, object] | None = None):
    if _TRACER is None:
        yield None
        return
    with _TRACER.start_as_current_span(name) as span:  # pragma: no cover - telemetry passthrough
        if attributes:
            for key, value in attributes.items():
                try:
                    span.set_attribute(key, value)
                except Exception:
                    continue
        yield span


@dataclass(slots=True)
class IngestionPlan:
    """Declarative description of the ingestion jobs to execute."""

    jobs: Sequence[BaseIngestionJob] = field(default_factory=tuple)
    limit: int | None = None


def _default_jobs() -> List[BaseIngestionJob]:
    jobs: List[BaseIngestionJob] = []
    for job_cls in (
        ChEMBLIngestion,
        BindingDBIngestion,
        PDSPKiIngestion,
        IUPHARIngestion,
        IndraIngestion,
        AllenAtlasIngestion,
        EBrainsAtlasIngestion,
        OpenAlexIngestion,
        SemanticScholarIngestion,
    ):
        try:
            jobs.append(job_cls())
        except Exception as exc:  # pragma: no cover - depends on optional deps/network
            LOGGER.debug("Skipping %s ingestion: %s", job_cls.__name__, exc)
    return jobs


def _store_is_empty(store: GraphStore) -> bool:
    try:
        if store.all_nodes():
            return False
    except NotImplementedError:  # pragma: no cover - backend without fast listing
        pass
    try:
        if store.all_edges():
            return False
    except NotImplementedError:  # pragma: no cover
        pass
    return True


def load_seed_graph(graph_service: GraphService, seed_path: Path | None = None) -> bool:
    """Load a cached graph snapshot into ``graph_service``.

    The helper is intentionally forgiving: malformed entries are skipped while
    logging a warning.  It returns ``True`` when at least one node or edge was
    persisted.
    """

    path = seed_path or DEFAULT_SEED_PATH
    if not path.exists():
        LOGGER.info("Seed graph file not found at %s", path)
        return False
    with _telemetry_span("ingest.load_seed_graph", {"seed_path": str(path)}):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Failed to load seed graph at %s: %s", path, exc)
            return False

    nodes: List[Node] = []
    edges: List[Edge] = []

    for raw_node in payload.get("nodes", []):
        try:
            category = BiolinkEntity(raw_node.get("category", BiolinkEntity.NAMED_THING))
            node = Node(
                id=str(raw_node.get("id")),
                name=str(raw_node.get("name", raw_node.get("id", "Unnamed"))),
                category=category,
                description=raw_node.get("description"),
                provided_by=raw_node.get("provided_by"),
                synonyms=list(raw_node.get("synonyms", [])),
                xrefs=list(raw_node.get("xrefs", [])),
                attributes=dict(raw_node.get("attributes", {})),
            )
            nodes.append(node)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Skipping malformed node entry %s: %s", raw_node, exc)

    for raw_edge in payload.get("edges", []):
        try:
            predicate = BiolinkPredicate(raw_edge.get("predicate", BiolinkPredicate.RELATED_TO))
        except ValueError:
            LOGGER.warning("Unknown predicate for seed edge: %s", raw_edge)
            continue
        try:
            evidence_items = [
                Evidence(
                    source=str(ev.get("source")),
                    reference=ev.get("reference"),
                    confidence=ev.get("confidence"),
                    uncertainty=ev.get("uncertainty"),
                    annotations=dict(ev.get("annotations", {})),
                )
                for ev in raw_edge.get("evidence", [])
                if ev.get("source")
            ]
            edge = Edge(
                subject=str(raw_edge.get("subject")),
                predicate=predicate,
                object=str(raw_edge.get("object")),
                relation=str(raw_edge.get("relation", "biolink:related_to")),
                knowledge_level=raw_edge.get("knowledge_level"),
                confidence=raw_edge.get("confidence"),
                publications=list(raw_edge.get("publications", [])),
                evidence=evidence_items,
                qualifiers=dict(raw_edge.get("qualifiers", {})),
            )
            edges.append(edge)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Skipping malformed edge entry %s: %s", raw_edge, exc)

    if not nodes and not edges:
        LOGGER.info("Seed graph %s did not provide any nodes or edges", path)
        return False

    graph_service.persist(nodes, edges)
    LOGGER.info("Loaded %d nodes and %d edges from seed graph", len(nodes), len(edges))
    return True


def execute_jobs(
    graph_service: GraphService,
    jobs: Sequence[BaseIngestionJob],
    *,
    limit: int | None = None,
    strict: bool = False,
) -> List[IngestionReport]:
    """Run ingestion ``jobs`` sequentially, persisting each fragment."""

    reports: List[IngestionReport] = []
    store = graph_service.store
    for job in jobs:
        with _telemetry_span("ingest.job", {"job.name": job.name}):
            report = IngestionReport(name=job.name)
            try:
                iterator: Iterable[dict] = job.fetch(limit=limit)
            except Exception as exc:  # pragma: no cover - network failure / optional deps
                LOGGER.warning("Failed to fetch records for %s: %s", job.name, exc)
                if strict:
                    raise
                continue
            try:
                iterable: TypingIterator[dict]
                if isinstance(iterator, Iterator):
                    iterable = iterator  # type: ignore[assignment]
                else:
                    iterable = iter(iterator)
                for idx, record in enumerate(iterable):
                    with _telemetry_span(
                        "ingest.job.record",
                        {"job.name": job.name, "record.index": idx},
                    ):
                        nodes, edges = job.transform(record)
                        if nodes or edges:
                            graph_service.persist(nodes, edges)
                        report.records_processed += 1
                        report.nodes_created += len(nodes)
                        report.edges_created += len(edges)
                        if limit is not None and report.records_processed >= limit:
                            break
            except Exception as exc:  # pragma: no cover - transformation failure
                LOGGER.warning("Ingestion job %s failed: %s", job.name, exc)
                if strict:
                    raise
                continue
            reports.append(report)
    return reports


def bootstrap_graph(
    graph_service: GraphService,
    *,
    plan: IngestionPlan | None = None,
    seed_path: Path | None = None,
    use_seed: bool = True,
    strict: bool = False,
) -> List[IngestionReport]:
    """Ensure the graph has baseline content before serving requests."""

    store = graph_service.store
    if not graph_service.config.is_memory_only and not _store_is_empty(store):
        LOGGER.info(
            "Graph backend %s already initialised; automatic bootstrap skipped",
            graph_service.config.backend,
        )
        return []

    if not _store_is_empty(store):
        LOGGER.debug("Graph store already populated; bootstrap skipped")
        return []

    jobs = list(plan.jobs) if plan else _default_jobs()
    if not jobs:
        LOGGER.warning("No ingestion jobs available for bootstrap")
        return []

    limit = plan.limit if plan else None
    with _telemetry_span(
        "ingest.bootstrap",
        {
            "job.count": len(jobs),
            "use_seed": bool(use_seed),
            "strict": bool(strict),
        },
    ):
        if use_seed:
            load_seed_graph(graph_service, seed_path=seed_path)
        reports = execute_jobs(graph_service, jobs, limit=limit, strict=strict)
    LOGGER.info("Completed bootstrap ingestion with %d job(s)", len(reports))
    return reports


__all__ = [
    "IngestionPlan",
    "bootstrap_graph",
    "execute_jobs",
    "load_seed_graph",
    "DEFAULT_SEED_PATH",
]
