"""FastAPI route declarations for the Neuropharm Simulation API."""

from __future__ import annotations

from typing import Iterable, List

from fastapi import APIRouter, Depends, HTTPException

from ..graph.models import Edge, Evidence, Node
from ..graph.service import GraphService
from ..engine.simulator import SimulationEngine, SimulationError
from .schemas import (
    Citation,
    EvidenceEdge,
    EvidenceRecord,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
    ExplainRequest,
    ExplainResponse,
    Explanation,
    GapDescriptor,
    GapsRequest,
    GapsResponse,
    GraphEdge,
    GraphExpandRequest,
    GraphExpandResponse,
    GraphNode,
    Pagination,
    PredictEffectsRequest,
    PredictEffectsResponse,
    PredictedEffect,
    Provenance,
    SimulationRequest,
    SimulationResponse,
)

api_router = APIRouter()

_graph_service = GraphService()
_simulation_engine = SimulationEngine()


def get_graph_service() -> GraphService:
    """Return the singleton GraphService used by the API layer."""

    return _graph_service


def get_simulation_engine() -> SimulationEngine:
    """Return the simulation engine instance."""

    return _simulation_engine


def _build_provenance(source: str, notes: str | None = None) -> Provenance:
    return Provenance(source=source, notes=notes)


def _convert_evidence(items: Iterable[Evidence]) -> List[EvidenceRecord]:
    return [
        EvidenceRecord(
            source=item.source,
            reference=item.reference,
            confidence=item.confidence,
            uncertainty=item.uncertainty,
            annotations=dict(item.annotations),
        )
        for item in items
    ]


def _convert_edge(edge: Edge, evidence: List[EvidenceRecord]) -> EvidenceEdge:
    return EvidenceEdge(
        subject=edge.subject,
        predicate=edge.predicate,
        object=edge.object,
        relation=edge.relation,
        knowledge_level=edge.knowledge_level,
        confidence=edge.confidence,
        qualifiers=dict(edge.qualifiers),
        evidence=evidence,
    )


def _convert_node(node: Node) -> GraphNode:
    return GraphNode(
        id=node.id,
        name=node.name,
        category=node.category,
        description=node.description,
        provided_by=node.provided_by,
        synonyms=list(node.synonyms),
        xrefs=list(node.xrefs),
        attributes=dict(node.attributes),
    )


def _convert_graph_edge(edge: Edge) -> GraphEdge:
    return GraphEdge(
        subject=edge.subject,
        predicate=edge.predicate,
        object=edge.object,
        relation=edge.relation,
        qualifiers=dict(edge.qualifiers),
    )


@api_router.post("/evidence/search", response_model=EvidenceSearchResponse, tags=["Evidence"])
def search_evidence(
    request: EvidenceSearchRequest,
    service: GraphService = Depends(get_graph_service),
) -> EvidenceSearchResponse:
    filters = request.filters
    predicate = filters.predicate.value if filters.predicate else None
    summaries = service.get_evidence(
        subject=filters.subject,
        predicate=predicate,
        object_=filters.object_,
    )

    results: List[EvidenceSearchResult] = []
    for summary in summaries:
        filtered = []
        for ev in summary.evidence:
            if filters.source and ev.source.lower() != filters.source.lower():
                continue
            if filters.min_confidence is not None:
                if ev.confidence is None or ev.confidence < filters.min_confidence:
                    continue
            filtered.append(ev)
        if not filtered:
            continue
        evidence_models = _convert_evidence(filtered)
        edge_model = _convert_edge(summary.edge, evidence_models)
        results.append(
            EvidenceSearchResult(
                edge=edge_model,
                total_evidence=len(evidence_models),
            )
        )

    total = len(results)
    page = request.pagination.page
    size = request.pagination.size
    start = (page - 1) * size
    end = start + size
    paged_results = results[start:end]

    return EvidenceSearchResponse(
        results=paged_results,
        pagination=Pagination(page=page, size=size),
        filters=filters,
        provenance=_build_provenance("graph-service", "Evidence search via GraphService.get_evidence"),
        total=total,
    )


@api_router.post("/graph/expand", response_model=GraphExpandResponse, tags=["Graph"])
def expand_graph(
    request: GraphExpandRequest,
    service: GraphService = Depends(get_graph_service),
) -> GraphExpandResponse:
    fragment = service.expand(request.node_id, depth=request.depth, limit=request.limit)
    nodes = [_convert_node(node) for node in fragment.nodes]

    if request.category_filter:
        allowed = set(request.category_filter)
        nodes = [node for node in nodes if node.category in allowed]

    node_ids = {node.id for node in nodes}
    edges = []
    for edge in fragment.edges:
        if node_ids and (edge.subject not in node_ids or edge.object not in node_ids):
            continue
        edges.append(_convert_graph_edge(edge))

    return GraphExpandResponse(
        nodes=nodes[: request.limit],
        edges=edges[: request.limit * 2],
        provenance=_build_provenance("graph-service", "Graph expansion performed using GraphService.neighbors"),
        pagination=Pagination(page=1, size=min(request.limit, max(len(nodes), 1))),
    )


@api_router.post("/predict/effects", response_model=PredictEffectsResponse, tags=["Simulation"])
def predict_effects(
    request: PredictEffectsRequest,
    engine: SimulationEngine = Depends(get_simulation_engine),
) -> PredictEffectsResponse:
    sim = request.simulation
    sim_payload = sim.model_dump()
    try:
        result = engine.run(
            sim_payload["receptors"],
            acute_1a=sim_payload["acute_1a"],
            adhd=sim_payload["adhd"],
            gut_bias=sim_payload["gut_bias"],
            pvt_weight=sim_payload["pvt_weight"],
        )
    except SimulationError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sorted_scores = sorted(result.scores.items(), key=lambda item: item[1], reverse=True)
    predicted: List[PredictedEffect] = []
    for metric, score in sorted_scores[: request.top_n]:
        rationale_segments: List[str] = []
        for receptor, refs in result.citations.items():
            if refs:
                rationale_segments.append(f"{receptor}: {len(refs)} refs")
        rationale = "; ".join(rationale_segments) or "No supporting citations available."
        predicted.append(PredictedEffect(metric=metric, score=score, rationale=rationale))

    return PredictEffectsResponse(
        compound_id=request.compound_id,
        requested=request,
        predicted_effects=predicted,
        provenance=_build_provenance("simulation-engine", "Derived from simulation score ranking."),
    )


@api_router.post("/simulate", response_model=SimulationResponse, tags=["Simulation"])
def run_simulation(
    request: SimulationRequest,
    engine: SimulationEngine = Depends(get_simulation_engine),
) -> SimulationResponse:
    payload = request.model_dump()
    try:
        result = engine.run(
            payload["receptors"],
            acute_1a=payload["acute_1a"],
            adhd=payload["adhd"],
            gut_bias=payload["gut_bias"],
            pvt_weight=payload["pvt_weight"],
        )
    except SimulationError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    citations = {
        receptor: [Citation(**ref) for ref in refs]
        for receptor, refs in result.citations.items()
    }

    return SimulationResponse(
        scores=result.scores,
        details=result.details,
        citations=citations,
        provenance=_build_provenance("simulation-engine", "Outputs produced by the Neuropharm simulation engine."),
    )


@api_router.post("/explain", response_model=ExplainResponse, tags=["Evidence"])
def explain_relationship(
    request: ExplainRequest,
    service: GraphService = Depends(get_graph_service),
) -> ExplainResponse:
    predicate = request.predicate.value if request.predicate else None
    summaries = service.get_evidence(
        subject=request.subject,
        predicate=predicate,
        object_=request.object_,
    )
    explanations: List[Explanation] = []
    for summary in summaries:
        evidence = _convert_evidence(summary.evidence[: request.max_evidence])
        if not evidence:
            continue
        explanations.append(
            Explanation(
                subject=summary.edge.subject,
                predicate=summary.edge.predicate,
                object=summary.edge.object,
                evidence=evidence,
            )
        )

    return ExplainResponse(
        explanations=explanations,
        provenance=_build_provenance("graph-service", "Explanation synthesised from direct evidence."),
    )


@api_router.post("/gaps", response_model=GapsResponse, tags=["Graph"])
def find_gaps(
    request: GapsRequest,
    service: GraphService = Depends(get_graph_service),
) -> GapsResponse:
    gaps = service.find_gaps(request.focus_nodes)
    descriptors = [
        GapDescriptor(subject=gap.subject, object=gap.object, reason=gap.reason)
        for gap in gaps
    ]
    return GapsResponse(
        gaps=descriptors,
        provenance=_build_provenance("graph-service", "Gap analysis across provided focus nodes."),
        total=len(descriptors),
    )


__all__ = [
    "api_router",
    "get_graph_service",
    "get_simulation_engine",
]
