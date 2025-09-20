from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from fastapi import APIRouter, HTTPException, status

from ..engine.receptors import (
    RECEPTORS,
    canonical_receptor_name,
    get_mechanism_factor,
    get_receptor_weights,
)
from ..graph.models import Edge, Node
from ..graph.service import EvidenceSummary, GraphService
from ..simulation import EngineRequest, ReceptorEngagement, SimulationEngine
from .schemas import (
    BaseSimulationRequest,
    Citation,
    EdgeSummary,
    EvidenceDetail,
    EvidenceSearchRequest,
    ExplainRequest,
    ExplainResponse,
    ExplanationDriver,
    GraphExpandRequest,
    GraphFragmentResponse,
    GraphGapItem,
    GraphGapRequest,
    GraphGapResponse,
    NodeSummary,
    PaginatedEvidenceResponse,
    PredictEffectsRequest,
    PredictEffectsResponse,
    ReceptorContribution,
    SimulationDetails,
    SimulationRequest,
    SimulationResponse,
)

SCORE_NAME_MAP: Dict[str, str] = {
    "drive": "DriveInvigoration",
    "apathy": "ApathyBlunting",
    "motivation": "Motivation",
    "cognitive_flexibility": "CognitiveFlexibility",
    "anxiety": "Anxiety",
    "sleep_quality": "SleepQuality",
}
SCORE_TO_METRIC = {value.lower(): key for key, value in SCORE_NAME_MAP.items()}
SCORE_TO_METRIC.update({key: key for key in SCORE_NAME_MAP})

REFS_PATH = Path(__file__).resolve().parents[1] / "refs.json"


def _load_receptor_refs() -> Dict[str, List[Dict[str, str]]]:
    try:
        with REFS_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return {key: list(value) for key, value in data.items()}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    return {}


RECEPTOR_REFS = _load_receptor_refs()


@dataclass(slots=True)
class _ReceptorBreakdown:
    receptor: str
    canonical: str
    mechanism: str
    occupancy: float
    metrics: Dict[str, float]
    evidence: float
    citations: List[Citation]


def _edge_to_summary(edge: Edge) -> EdgeSummary:
    return EdgeSummary(
        subject=edge.subject,
        predicate=edge.predicate,
        object=edge.object,
        relation=edge.relation,
        knowledge_level=edge.knowledge_level,
        confidence=edge.confidence,
        publications=list(edge.publications),
        evidence=[
            EvidenceDetail(
                source=ev.source,
                reference=ev.reference,
                confidence=ev.confidence,
                uncertainty=ev.uncertainty,
                annotations=dict(ev.annotations),
            )
            for ev in edge.evidence
        ],
        qualifiers=dict(edge.qualifiers),
        created_at=edge.created_at.isoformat(),
    )


def _summary_to_model(summary: EvidenceSummary) -> EdgeSummary:
    return _edge_to_summary(summary.edge)


def _node_to_summary(node: Node) -> NodeSummary:
    return NodeSummary(
        id=node.id,
        name=node.name,
        category=node.category,
        description=node.description,
        provided_by=node.provided_by,
        synonyms=list(node.synonyms),
        xrefs=list(node.xrefs),
        attributes=dict(node.attributes),
    )


def _evidence_level(canonical: str) -> float:
    references = RECEPTOR_REFS.get(canonical, [])
    return min(0.95, 0.45 + 0.1 * len(references))


def _citations_for(canonical: str) -> List[Citation]:
    return [Citation(**ref) for ref in RECEPTOR_REFS.get(canonical, [])]


def _apply_modifiers(
    entries: List[_ReceptorBreakdown], request: BaseSimulationRequest
) -> Tuple[List[_ReceptorBreakdown], Dict[str, float], Dict[str, float]]:
    modifiers: Dict[str, float] = {}

    if request.gut_bias:
        for entry in entries:
            entry.metrics = {
                metric: value * 0.9 if value < 0 else value for metric, value in entry.metrics.items()
            }
    if request.acute_1a:
        for entry in entries:
            entry.metrics = {metric: value * 0.75 for metric, value in entry.metrics.items()}

    scale = 1.0 - request.pvt_weight * 0.2
    for entry in entries:
        entry.metrics = {metric: value * scale for metric, value in entry.metrics.items()}

    totals = {metric: sum(entry.metrics.get(metric, 0.0) for entry in entries) for metric in SCORE_NAME_MAP}

    if request.adhd:
        totals["drive"] -= 0.3
        totals["motivation"] -= 0.2
        modifiers[SCORE_NAME_MAP["drive"]] = modifiers.get(SCORE_NAME_MAP["drive"], 0.0) - 6.0
        modifiers[SCORE_NAME_MAP["motivation"]] = modifiers.get(SCORE_NAME_MAP["motivation"], 0.0) - 4.0

    return entries, modifiers, totals


def _compute_effects(request: BaseSimulationRequest) -> Tuple[
    Dict[str, float],
    List[ReceptorContribution],
    Dict[str, float],
    Dict[str, float],
    List[str],
]:
    ignored: List[str] = []
    breakdown: List[_ReceptorBreakdown] = []

    for supplied_name, spec in request.receptors.items():
        canonical = canonical_receptor_name(supplied_name)
        if canonical not in RECEPTORS:
            ignored.append(supplied_name)
            continue
        weights = get_receptor_weights(canonical)
        factor = get_mechanism_factor(spec.mech)
        metrics = {
            metric: float(weights.get(metric, 0.0)) * spec.occ * factor for metric in SCORE_NAME_MAP
        }
        breakdown.append(
            _ReceptorBreakdown(
                receptor=supplied_name,
                canonical=canonical,
                mechanism=spec.mech,
                occupancy=spec.occ,
                metrics=metrics,
                evidence=_evidence_level(canonical),
                citations=_citations_for(canonical),
            )
        )

    entries, modifiers, totals = _apply_modifiers(breakdown, request)

    scores: Dict[str, float] = {}
    for metric, score_name in SCORE_NAME_MAP.items():
        change = 20.0 * totals.get(metric, 0.0)
        if metric == "apathy":
            value = 50.0 - change
        else:
            value = 50.0 + change
        scores[score_name] = float(max(0.0, min(100.0, value)))

    contributions: List[ReceptorContribution] = []
    for entry in entries:
        score_delta = {}
        for metric, score_name in SCORE_NAME_MAP.items():
            change = 20.0 * entry.metrics.get(metric, 0.0)
            if metric == "apathy":
                change *= -1.0
            score_delta[score_name] = float(change)
        contributions.append(
            ReceptorContribution(
                receptor=entry.receptor,
                canonical_receptor=entry.canonical,
                mechanism=entry.mechanism,
                occupancy=entry.occupancy,
                score_delta=score_delta,
                evidence=entry.evidence,
                uncertainty=float(max(0.0, min(1.0, 1.0 - entry.evidence))),
                citations=list(entry.citations),
            )
        )

    evidence_levels = [entry.evidence for entry in entries if entry.evidence is not None]
    mean_evidence = sum(evidence_levels) / len(evidence_levels) if evidence_levels else 0.5
    uncertainty = {
        score_name: float(max(0.05, 1.0 - mean_evidence)) for score_name in SCORE_NAME_MAP.values()
    }

    return scores, contributions, uncertainty, modifiers, ignored


def _build_engine_request(payload: SimulationRequest) -> Tuple[EngineRequest, Dict[str, List[Citation]], List[str]]:
    regimen = payload.dosing
    if payload.acute_1a:
        regimen = "acute"

    engagements: Dict[str, ReceptorEngagement] = {}
    ignored: List[str] = []

    for supplied_name, spec in payload.receptors.items():
        canonical = canonical_receptor_name(supplied_name)
        if canonical not in RECEPTORS:
            ignored.append(supplied_name)
            continue
        weights = get_receptor_weights(canonical)
        if weights:
            kg_weight = sum(abs(weight) for weight in weights.values()) / len(weights)
        else:
            kg_weight = 0.25
        engagements[canonical] = ReceptorEngagement(
            name=canonical,
            occupancy=spec.occ,
            mechanism=spec.mech,
            kg_weight=kg_weight,
            evidence=_evidence_level(canonical),
        )

    engine_request = EngineRequest(
        receptors=engagements,
        regimen=regimen,
        adhd=payload.adhd,
        gut_bias=payload.gut_bias,
        pvt_weight=payload.pvt_weight,
    )

    citations = {
        canonical: _citations_for(canonical)
        for canonical in engagements.keys()
        if RECEPTOR_REFS.get(canonical)
    }

    return engine_request, citations, ignored


def create_router(
    graph_service: GraphService | None = None,
    simulation_engine: SimulationEngine | None = None,
) -> APIRouter:
    service = graph_service or GraphService()
    engine = simulation_engine or SimulationEngine(time_step=1.0)

    router = APIRouter()

    @router.post("/evidence/search", response_model=PaginatedEvidenceResponse)
    def search_evidence(payload: EvidenceSearchRequest) -> PaginatedEvidenceResponse:
        predicate_raw = payload.predicate
        predicate = predicate_raw.value if hasattr(predicate_raw, "value") else predicate_raw
        summaries = service.get_evidence(
            subject=payload.subject,
            predicate=predicate,
            object_=payload.object,
        )
        total = len(summaries)
        start = (payload.page - 1) * payload.page_size
        end = start + payload.page_size
        page_items = summaries[start:end]
        return PaginatedEvidenceResponse(
            results=[_summary_to_model(summary) for summary in page_items],
            page=payload.page,
            page_size=payload.page_size,
            total=total,
        )

    @router.post("/graph/expand", response_model=GraphFragmentResponse)
    def expand_graph(payload: GraphExpandRequest) -> GraphFragmentResponse:
        fragment = service.expand(node_id=payload.node_id, depth=payload.depth, limit=payload.limit)
        nodes = [_node_to_summary(node) for node in fragment.nodes]
        edges = [_edge_to_summary(edge) for edge in fragment.edges]
        return GraphFragmentResponse(nodes=nodes, edges=edges)

    @router.post("/predict/effects", response_model=PredictEffectsResponse)
    def predict_effects(payload: PredictEffectsRequest) -> PredictEffectsResponse:
        scores, contributions, uncertainty, modifiers, ignored = _compute_effects(payload)
        return PredictEffectsResponse(
            scores=scores,
            contributions=contributions,
            uncertainty=uncertainty,
            modifiers=modifiers,
            ignored_targets=ignored,
        )

    @router.post("/simulate", response_model=SimulationResponse)
    def simulate(payload: SimulationRequest) -> SimulationResponse:
        engine_request, citations, ignored = _build_engine_request(payload)
        try:
            result = engine.run(engine_request)
        except ValueError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        details = SimulationDetails(
            timepoints=result.timepoints,
            trajectories=result.trajectories,
            modules=result.module_summaries,
            ignored_receptors=ignored,
        )
        return SimulationResponse(
            scores=result.scores,
            details=details,
            citations=citations,
            confidence=result.confidence,
        )

    @router.post("/explain", response_model=ExplainResponse)
    def explain(payload: ExplainRequest) -> ExplainResponse:
        scores, contributions, uncertainty, modifiers, ignored = _compute_effects(payload)
        metric_key: str
        if payload.metric:
            lookup = payload.metric.lower()
            if lookup not in SCORE_TO_METRIC:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unknown metric '{payload.metric}'.",
                )
            metric_key = SCORE_TO_METRIC[lookup]
        else:
            metric_key = "motivation"
        score_name = SCORE_NAME_MAP[metric_key]
        predicted_score = scores.get(score_name, 50.0)

        sorted_contribs = sorted(
            contributions,
            key=lambda contrib: abs(contrib.score_delta.get(score_name, 0.0)),
            reverse=True,
        )
        drivers: List[ExplanationDriver] = []
        for contrib in sorted_contribs[:3]:
            delta = contrib.score_delta.get(score_name, 0.0)
            drivers.append(
                ExplanationDriver(
                    receptor=contrib.receptor,
                    canonical_receptor=contrib.canonical_receptor,
                    mechanism=contrib.mechanism,
                    score_delta=delta,
                    confidence=float(max(0.0, min(1.0, 1.0 - contrib.uncertainty))),
                    citations=contrib.citations,
                )
            )

        if not drivers:
            summary = (
                f"{score_name} is predicted at {predicted_score:.1f} (Δ {predicted_score - 50.0:+.1f}) "
                "without recognised receptor drivers."
            )
        else:
            top_phrases = []
            for driver in drivers:
                direction = "raises" if driver.score_delta >= 0 else "lowers"
                top_phrases.append(
                    f"{driver.canonical_receptor} ({driver.mechanism}) {direction} the score by {abs(driver.score_delta):.1f}"
                )
            modifier_delta = modifiers.get(score_name, 0.0)
            modifier_clause = ""
            if modifier_delta:
                modifier_clause = f" Phenotype modifiers contribute {modifier_delta:+.1f}."
            summary = (
                f"{score_name} is predicted at {predicted_score:.1f} (Δ {predicted_score - 50.0:+.1f}). "
                f"Key drivers: {', '.join(top_phrases)}.{modifier_clause}"
            )
        summary += f" Estimated uncertainty {uncertainty.get(score_name, 0.5):.2f}."

        return ExplainResponse(
            metric=score_name,
            predicted_score=predicted_score,
            summary=summary,
            drivers=drivers,
            uncertainty=uncertainty.get(score_name, 0.5),
            modifiers=modifiers,
            ignored_targets=ignored,
        )

    @router.post("/gaps", response_model=GraphGapResponse)
    def graph_gaps(payload: GraphGapRequest) -> GraphGapResponse:
        gaps = service.find_gaps(payload.focus)
        items = [GraphGapItem(subject=gap.subject, object=gap.object, reason=gap.reason) for gap in gaps]
        return GraphGapResponse(gaps=items)

    return router
