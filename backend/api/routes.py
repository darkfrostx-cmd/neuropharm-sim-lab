"""FastAPI router wiring knowledge graph and simulation services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, status

from ..engine.receptors import RECEPTORS, canonical_receptor_name, get_receptor_weights
from ..graph.models import BiolinkPredicate
from ..graph.service import EvidenceSummary, GraphService
from ..simulation import (
    EngineRequest,
    GraphBackedReceptorAdapter,
    ReceptorEngagement,
    SimulationEngine,
)
from . import schemas


@dataclass
class ServiceRegistry:
    """Container bundling service layer dependencies for the API."""

    graph_service: GraphService = field(default_factory=GraphService)
    simulation_engine: SimulationEngine = field(default_factory=lambda: SimulationEngine(time_step=1.0))
    receptor_adapter: GraphBackedReceptorAdapter | None = None
    receptor_references: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.receptor_adapter is None:
            self.receptor_adapter = GraphBackedReceptorAdapter(self.graph_service)

    def configure(
        self,
        *,
        graph_service: GraphService | None = None,
        simulation_engine: SimulationEngine | None = None,
        receptor_adapter: GraphBackedReceptorAdapter | None = None,
        receptor_references: Dict[str, List[Dict[str, str]]] | None = None,
    ) -> None:
        if graph_service is not None:
            self.graph_service = graph_service
        if simulation_engine is not None:
            self.simulation_engine = simulation_engine
        if receptor_adapter is not None:
            self.receptor_adapter = receptor_adapter
        elif getattr(self, "receptor_adapter", None) is None:
            self.receptor_adapter = GraphBackedReceptorAdapter(self.graph_service)
        if receptor_references is not None:
            self.receptor_references = receptor_references


services = ServiceRegistry()


def configure_services(
    *,
    graph_service: GraphService | None = None,
    simulation_engine: SimulationEngine | None = None,
    receptor_adapter: GraphBackedReceptorAdapter | None = None,
    receptor_references: Dict[str, List[Dict[str, str]]] | None = None,
) -> None:
    """Configure the shared service registry used by API routes."""

    services.configure(
        graph_service=graph_service,
        simulation_engine=simulation_engine,
        receptor_adapter=receptor_adapter,
        receptor_references=receptor_references,
    )


def get_services() -> ServiceRegistry:
    return services


def _http_error(status_code: int, code: str, message: str, *, context: Dict[str, object] | None = None) -> HTTPException:
    payload = schemas.ErrorPayload(code=code, message=message, context=context or {})
    return HTTPException(status_code=status_code, detail=payload.model_dump())


router = APIRouter()


@router.post("/evidence/search", response_model=schemas.EvidenceSearchResponse)
def search_evidence(
    request: schemas.EvidenceSearchRequest,
    svc: ServiceRegistry = Depends(get_services),
) -> schemas.EvidenceSearchResponse:
    predicate_value: str | None = request.predicate.value if isinstance(request.predicate, BiolinkPredicate) else None
    summaries: List[EvidenceSummary] = svc.graph_service.get_evidence(
        subject=request.subject,
        predicate=predicate_value,
        object_=request.object_,
    )
    total = len(summaries)
    start = (request.page - 1) * request.size
    end = start + request.size
    page_items = summaries[start:end]
    items = [schemas.EvidenceHit.from_domain(summary.edge, summary.evidence) for summary in page_items]
    return schemas.EvidenceSearchResponse(page=request.page, size=request.size, total=total, items=items)


@router.post("/graph/expand", response_model=schemas.GraphExpandResponse)
def expand_graph(
    request: schemas.GraphExpandRequest,
    svc: ServiceRegistry = Depends(get_services),
) -> schemas.GraphExpandResponse:
    store = getattr(svc.graph_service, "store", None)
    if store is None or store.get_node(request.node_id) is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "node_not_found",
            f"Node '{request.node_id}' not found in knowledge graph.",
            context={"node_id": request.node_id},
        )
    fragment = svc.graph_service.expand(request.node_id, depth=request.depth, limit=request.limit)
    nodes = [schemas.GraphNode.from_domain(node) for node in fragment.nodes]
    edges = [schemas.GraphEdge.from_domain(edge) for edge in fragment.edges]
    return schemas.GraphExpandResponse(centre=request.node_id, nodes=nodes, edges=edges)


def _fallback_weight(receptor: str) -> float:
    try:
        weights = get_receptor_weights(receptor)
    except KeyError:
        return 0.25
    if not weights:
        return 0.25
    return float(sum(abs(value) for value in weights.values()) / len(weights))


def _fallback_evidence(receptor: str, references: Dict[str, List[Dict[str, str]]]) -> float:
    count = len(references.get(receptor, []))
    return float(min(0.95, 0.45 + 0.1 * count))


@router.post("/predict/effects", response_model=schemas.PredictEffectsResponse)
def predict_receptor_effects(
    request: schemas.PredictEffectsRequest,
    svc: ServiceRegistry = Depends(get_services),
) -> schemas.PredictEffectsResponse:
    adapter = svc.receptor_adapter
    if adapter is None:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "adapter_unavailable", "Receptor adapter not configured")
    if not request.receptors:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "empty_request", "At least one receptor must be supplied")
    items: List[schemas.ReceptorEffect] = []
    for receptor_query in request.receptors:
        canon = canonical_receptor_name(receptor_query.name)
        if canon not in RECEPTORS:
            raise _http_error(
                status.HTTP_404_NOT_FOUND,
                "receptor_not_supported",
                f"Receptor '{receptor_query.name}' is not recognised by the simulation engine.",
                context={"receptor": receptor_query.name},
            )
        fallback_weight = receptor_query.fallback_weight if receptor_query.fallback_weight is not None else _fallback_weight(canon)
        fallback_evidence = (
            receptor_query.fallback_evidence
            if receptor_query.fallback_evidence is not None
            else _fallback_evidence(canon, svc.receptor_references)
        )
        bundle = adapter.derive(canon, fallback_weight=fallback_weight, fallback_evidence=fallback_evidence)
        uncertainty = float(max(0.0, min(1.0, 1.0 - bundle.evidence_score)))
        items.append(
            schemas.ReceptorEffect(
                receptor=canon,
                kg_weight=bundle.kg_weight,
                evidence=bundle.evidence_score,
                affinity=bundle.affinity,
                expression=bundle.expression,
                evidence_sources=list(bundle.evidence_sources),
                evidence_items=bundle.evidence_count,
                uncertainty=uncertainty,
            )
        )
    return schemas.PredictEffectsResponse(items=items)


@router.post("/simulate", response_model=schemas.SimulationResponse)
def run_simulation(
    request: schemas.SimulationRequest,
    svc: ServiceRegistry = Depends(get_services),
) -> schemas.SimulationResponse:
    adapter = svc.receptor_adapter
    if adapter is None:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "adapter_unavailable", "Receptor adapter not configured")
    regimen = "acute" if request.acute_1a else request.dosing
    engagements: Dict[str, ReceptorEngagement] = {}
    receptor_context: Dict[str, Dict[str, object]] = {}
    for raw_name, spec in request.receptors.items():
        canon = canonical_receptor_name(raw_name)
        if canon not in RECEPTORS:
            continue
        bundle = adapter.derive(
            canon,
            fallback_weight=_fallback_weight(canon),
            fallback_evidence=_fallback_evidence(canon, svc.receptor_references),
        )
        engagement = ReceptorEngagement(
            name=canon,
            occupancy=spec.occ,
            mechanism=spec.mech,
            kg_weight=bundle.kg_weight,
            evidence=bundle.evidence_score,
            affinity=bundle.affinity,
            expression=bundle.expression,
            evidence_sources=bundle.evidence_sources,
        )
        engagements[canon] = engagement
        receptor_context[canon] = {
            "kg_weight": bundle.kg_weight,
            "evidence": bundle.evidence_score,
            "affinity": bundle.affinity,
            "expression": bundle.expression,
            "sources": list(bundle.evidence_sources),
            "uncertainty": float(max(0.0, min(1.0, 1.0 - bundle.evidence_score))),
            "evidence_items": bundle.evidence_count,
        }
    if not engagements:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "no_receptors",
            "No recognised receptors were supplied in the payload.",
        )
    engine_request = EngineRequest(
        receptors=engagements,
        regimen=regimen,
        adhd=request.adhd,
        gut_bias=request.gut_bias,
        pvt_weight=request.pvt_weight,
    )
    try:
        result = svc.simulation_engine.run(engine_request)
    except ValueError as exc:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "simulation_failed", str(exc)) from exc
    citations = {
        canon: [schemas.Citation(**ref) for ref in svc.receptor_references.get(canon, [])]
        for canon in receptor_context
    }
    details = schemas.SimulationDetails(
        timepoints=result.timepoints,
        trajectories=result.trajectories,
        modules=result.module_summaries,
        receptor_context=receptor_context,
    )
    uncertainty = {
        metric: float(max(0.0, min(1.0, 1.0 - confidence)))
        for metric, confidence in result.confidence.items()
    }
    return schemas.SimulationResponse(
        scores=result.scores,
        details=details,
        citations=citations,
        confidence=result.confidence,
        uncertainty=uncertainty,
    )


def _collect_evidence(
    summaries: Iterable[EvidenceSummary],
    direction: str,
    seen: Set[Tuple[str, str, str, str]],
) -> List[schemas.ExplanationEdge]:
    items: List[schemas.ExplanationEdge] = []
    for summary in summaries:
        key = (*summary.edge.key, direction)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            schemas.ExplanationEdge(
                direction=direction,
                edge=schemas.GraphEdge.from_domain(summary.edge),
                provenance=[schemas.EvidenceProvenance.from_domain(ev) for ev in summary.evidence],
            )
        )
    return items


@router.post("/explain", response_model=schemas.ExplainResponse)
def explain_receptor(
    request: schemas.ExplainRequest,
    svc: ServiceRegistry = Depends(get_services),
) -> schemas.ExplainResponse:
    adapter = svc.receptor_adapter
    if adapter is None:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "adapter_unavailable", "Receptor adapter not configured")
    canon = canonical_receptor_name(request.receptor)
    if canon not in RECEPTORS:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "receptor_not_supported",
            f"Receptor '{request.receptor}' is not recognised by the simulation engine.",
            context={"receptor": request.receptor},
        )
    bundle = adapter.derive(
        canon,
        fallback_weight=_fallback_weight(canon),
        fallback_evidence=_fallback_evidence(canon, svc.receptor_references),
    )
    identifiers = adapter.identifiers_for(canon)
    items: List[schemas.ExplanationEdge] = []
    seen: Set[Tuple[str, str, str, str]] = set()
    if request.direction in {"both", "upstream"}:
        for identifier in identifiers:
            upstream = svc.graph_service.get_evidence(object_=identifier)
            items.extend(_collect_evidence(upstream, "upstream", seen))
    if request.direction in {"both", "downstream"}:
        for identifier in identifiers:
            downstream = svc.graph_service.get_evidence(subject=identifier)
            items.extend(_collect_evidence(downstream, "downstream", seen))
    items.sort(key=lambda item: item.edge.confidence or 0.0, reverse=True)
    items = items[: request.limit]
    causal_summary = None
    for explanation in items:
        if explanation.direction == "downstream":
            causal_summary = svc.graph_service.summarize_causal(canon, explanation.edge.object)
            if causal_summary is not None:
                break
    if causal_summary is None:
        for explanation in items:
            if explanation.direction == "upstream":
                causal_summary = svc.graph_service.summarize_causal(explanation.edge.subject, canon)
                if causal_summary is not None:
                    break
    causal_payload = (
        schemas.CausalDiagnostics.from_domain(causal_summary) if causal_summary is not None else None
    )
    uncertainty = float(max(0.0, min(1.0, 1.0 - bundle.evidence_score)))
    return schemas.ExplainResponse(
        receptor=request.receptor,
        canonical_receptor=canon,
        kg_weight=bundle.kg_weight,
        evidence=bundle.evidence_score,
        uncertainty=uncertainty,
        provenance=list(bundle.evidence_sources),
        edges=items,
        causal=causal_payload,
    )


@router.post("/gaps", response_model=schemas.GapResponse)
def find_graph_gaps(
    request: schemas.GapRequest,
    svc: ServiceRegistry = Depends(get_services),
) -> schemas.GapResponse:
    store = getattr(svc.graph_service, "store", None)
    if store is None:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "store_unavailable", "Graph store is not configured")
    missing = [node for node in request.focus_nodes if store.get_node(node) is None]
    if missing:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "nodes_not_found",
            "One or more focus nodes are absent from the knowledge graph.",
            context={"missing": missing},
        )
    gaps = svc.graph_service.find_gaps(request.focus_nodes)
    items: List[schemas.GapDescriptor] = []
    for gap in gaps:
        metadata = dict(gap.metadata)
        metadata.setdefault("context_weight", 1.0)
        metadata.setdefault("context_label", "")
        metadata.setdefault("raw_score", float(gap.embedding_score or 0.0))
        context_weight = float(metadata.get("context_weight", 1.0)) if metadata else 1.0
        raw_score = float(metadata.get("raw_score", gap.embedding_score or 0.0))
        impact_component = float(max(0.0, min(1.0, abs(gap.embedding_score or 0.0))))
        uncertainty = float(
            max(
                0.05,
                min(0.95, 1.0 - min(0.9, 0.3 * context_weight + 0.2 * impact_component)),
            )
        )
        causal_payload = schemas.CausalDiagnostics.from_domain(gap.causal) if gap.causal else None
        counterfactuals = [schemas.CounterfactualEstimate.from_domain(cf) for cf in gap.counterfactuals]
        items.append(
            schemas.GapDescriptor(
                subject=gap.subject,
                object=gap.object,
                predicate=gap.predicate.value,
                reason=gap.reason,
                embedding_score=gap.embedding_score,
                impact_score=gap.impact_score,
                context=metadata,
                literature=list(gap.literature),
                uncertainty=uncertainty,
                counterfactual_summary=gap.counterfactual_summary,
                counterfactuals=counterfactuals,
                causal=causal_payload,
            )
        )
    return schemas.GapResponse(items=items)


__all__ = ["router", "configure_services"]
