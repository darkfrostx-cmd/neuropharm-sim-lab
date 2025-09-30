"""Pydantic schemas used by the public API surface."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Sequence, Literal

from pydantic import BaseModel, Field

from ..atlas import AtlasCoordinate as DomainAtlasCoordinate
from ..atlas import AtlasOverlay as DomainAtlasOverlay
from ..atlas import AtlasVolume as DomainAtlasVolume
from ..graph.models import BiolinkPredicate, Edge, Evidence, Node
from ..reasoning import CausalSummary, CounterfactualScenario


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class ErrorPayload(BaseModel):
    """Standard error envelope returned by API endpoints."""

    code: str = Field(..., description="Machine readable error identifier")
    message: str = Field(..., description="Human readable explanation")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class EvidenceProvenance(BaseModel):
    """Metadata describing how a piece of evidence was sourced."""

    source: str | None = Field(default=None, description="Originating datasource")
    reference: str | None = Field(default=None, description="Reference identifier (PMID/DOI)")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty: str | None = Field(default=None, description="Qualitative uncertainty descriptor")
    annotations: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, evidence: Evidence) -> "EvidenceProvenance":
        return cls(
            source=evidence.source,
            reference=evidence.reference,
            confidence=evidence.confidence,
            uncertainty=evidence.uncertainty,
            annotations=dict(evidence.annotations),
        )


class GraphNode(BaseModel):
    """Serialised representation of a knowledge-graph node."""

    id: str
    name: str
    category: str
    description: str | None = None
    provided_by: str | None = None
    synonyms: Sequence[str] = Field(default_factory=list)
    xrefs: Sequence[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, node: Node) -> "GraphNode":
        return cls(
            id=node.id,
            name=node.name,
            category=node.category.value,
            description=node.description,
            provided_by=node.provided_by,
            synonyms=list(node.synonyms),
            xrefs=list(node.xrefs),
            attributes=dict(node.attributes),
        )


class GraphEdge(BaseModel):
    """Serialised representation of a graph edge with confidence metadata."""

    subject: str
    predicate: str
    object: str
    relation: str
    knowledge_level: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty: float | None = Field(default=None, ge=0.0, le=1.0)
    publications: Sequence[str] = Field(default_factory=list)
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_domain(cls, edge: Edge) -> "GraphEdge":
        confidence = edge.confidence if edge.confidence is not None else None
        uncertainty = None
        if confidence is not None:
            uncertainty = float(max(0.0, min(1.0, 1.0 - confidence)))
        return cls(
            subject=edge.subject,
            predicate=edge.predicate.value,
            object=edge.object,
            relation=edge.relation,
            knowledge_level=edge.knowledge_level,
            confidence=confidence,
            uncertainty=uncertainty,
            publications=list(edge.publications),
            qualifiers=dict(edge.qualifiers),
            created_at=edge.created_at,
        )


class EvidenceHit(BaseModel):
    """Evidence response entry for ``/evidence/search``."""

    edge: GraphEdge
    provenance: Sequence[EvidenceProvenance]

    @classmethod
    def from_domain(cls, edge: Edge, evidence: Iterable[Evidence]) -> "EvidenceHit":
        provenance = [EvidenceProvenance.from_domain(ev) for ev in evidence]
        return cls(edge=GraphEdge.from_domain(edge), provenance=provenance)


# ---------------------------------------------------------------------------
# Causal summary schemas
# ---------------------------------------------------------------------------


class CounterfactualEstimate(BaseModel):
    label: str
    treatment_value: float
    predicted_outcome: float

    @classmethod
    def from_domain(cls, scenario: CounterfactualScenario) -> "CounterfactualEstimate":
        return cls(
            label=scenario.label,
            treatment_value=scenario.treatment_value,
            predicted_outcome=scenario.predicted_outcome,
        )


class CausalDiagnostics(BaseModel):
    treatment: str
    outcome: str
    effect: float
    direction: str
    confidence: float
    n_treated: int
    n_control: int
    description: str
    assumption_graph: str | None = None
    counterfactuals: Sequence[CounterfactualEstimate] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, summary: CausalSummary) -> "CausalDiagnostics":
        return cls(
            treatment=summary.treatment,
            outcome=summary.outcome,
            effect=summary.effect,
            direction=summary.direction,
            confidence=summary.confidence,
            n_treated=summary.n_treated,
            n_control=summary.n_control,
            description=summary.description,
            assumption_graph=summary.assumption_graph,
            counterfactuals=[CounterfactualEstimate.from_domain(cf) for cf in summary.counterfactuals],
            diagnostics=dict(summary.diagnostics),
        )


# ---------------------------------------------------------------------------
# Evidence search schemas
# ---------------------------------------------------------------------------


class EvidenceSearchRequest(BaseModel):
    """Input filters for the evidence search endpoint."""

    subject: str | None = Field(default=None, description="Subject CURIE")
    predicate: BiolinkPredicate | None = Field(default=None)
    object_: str | None = Field(default=None, alias="object")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=25, ge=1, le=100)


class EvidenceSearchResponse(BaseModel):
    """Paginated evidence search result set."""

    page: int
    size: int
    total: int
    items: Sequence[EvidenceHit]


# ---------------------------------------------------------------------------
# Graph expansion schemas
# ---------------------------------------------------------------------------


class GraphExpandRequest(BaseModel):
    node_id: str = Field(..., description="Central node to expand around")
    depth: int = Field(default=1, ge=1, le=4)
    limit: int = Field(default=25, ge=1, le=200)


class GraphExpandResponse(BaseModel):
    centre: str
    nodes: Sequence[GraphNode]
    edges: Sequence[GraphEdge]


# ---------------------------------------------------------------------------
# Atlas overlays
# ---------------------------------------------------------------------------


class AtlasCoordinate(BaseModel):
    reference_space: int | None = Field(default=None)
    x_mm: float | None = Field(default=None)
    y_mm: float | None = Field(default=None)
    z_mm: float | None = Field(default=None)
    source: str

    @classmethod
    def from_domain(cls, coord: DomainAtlasCoordinate) -> "AtlasCoordinate":
        return cls(
            reference_space=coord.reference_space,
            x_mm=coord.x_mm,
            y_mm=coord.y_mm,
            z_mm=coord.z_mm,
            source=coord.source,
        )


class AtlasVolume(BaseModel):
    name: str
    url: str
    format: str
    description: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, volume: DomainAtlasVolume) -> "AtlasVolume":
        return cls(
            name=volume.name,
            url=volume.url,
            format=volume.format,
            description=volume.description,
            metadata=dict(volume.metadata),
        )


class AtlasOverlayRequest(BaseModel):
    node_id: str = Field(..., description="Node identifier used to retrieve atlas overlays")


class AtlasOverlayResponse(BaseModel):
    node_id: str
    provider: str
    coordinates: Sequence[AtlasCoordinate]
    volumes: Sequence[AtlasVolume]

    @classmethod
    def from_domain(cls, overlay: DomainAtlasOverlay) -> "AtlasOverlayResponse":
        return cls(
            node_id=overlay.node_id,
            provider=overlay.provider,
            coordinates=[AtlasCoordinate.from_domain(coord) for coord in overlay.coordinates],
            volumes=[AtlasVolume.from_domain(volume) for volume in overlay.volumes],
        )


# ---------------------------------------------------------------------------
# Predictive receptor evidence schemas
# ---------------------------------------------------------------------------


class ReceptorQuery(BaseModel):
    name: str = Field(..., description="Input receptor identifier")
    fallback_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    fallback_evidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ReceptorEffect(BaseModel):
    receptor: str
    kg_weight: float
    evidence: float
    affinity: float | None = None
    expression: float | None = None
    evidence_sources: Sequence[str] = Field(default_factory=list)
    evidence_items: int = 0
    uncertainty: float


class PredictEffectsRequest(BaseModel):
    receptors: Sequence[ReceptorQuery]


class PredictEffectsResponse(BaseModel):
    items: Sequence[ReceptorEffect]


# ---------------------------------------------------------------------------
# Simulation schemas
# ---------------------------------------------------------------------------


MechanismLiteral = Field(discriminator="mech")  # placeholder to keep IDEs quiet


Mechanism = Literal["agonist", "antagonist", "partial", "inverse"]


class ReceptorSpec(BaseModel):
    occ: float = Field(ge=0.0, le=1.0)
    mech: Mechanism


class SimulationAssumptions(BaseModel):
    trkB_facilitation: bool = Field(
        default=False,
        description="Enable BDNF/TrkB plasticity facilitation cascade",
    )
    alpha2a_hcn_closure: bool = Field(
        default=False,
        description="Assume α2A-mediated HCN channel closure boosting working memory",
    )
    mu_opioid_bonding: bool = Field(
        default=False,
        description="Engage μ-opioid social bonding microcircuit weights",
    )
    a2a_d2_heteromer: bool = Field(
        default=False,
        description="Include A2A–D2 heteromer facilitation of exploration bias",
    )
    alpha2c_gate: bool = Field(
        default=False,
        description="Enable α2C cortico-striatal gate dampening stress arousal",
    )

    class Config:
        extra = "forbid"


class SimulationRequest(BaseModel):
    receptors: Mapping[str, ReceptorSpec]
    acute_1a: bool = False
    dosing: Literal["acute", "chronic"] = "chronic"
    adhd: bool = False
    gut_bias: bool = False
    pvt_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    assumptions: SimulationAssumptions = Field(default_factory=SimulationAssumptions)


class Citation(BaseModel):
    title: str
    pmid: str | None = None
    doi: str | None = None


class SimulationDetails(BaseModel):
    timepoints: Sequence[float]
    trajectories: Mapping[str, Sequence[float]]
    modules: Dict[str, Any]
    receptor_context: Mapping[str, Dict[str, Any]]


class ControlledTerm(BaseModel):
    id: str
    label: str


class BehavioralTagAnnotation(BaseModel):
    label: str
    domain: str | None = None
    rdoc: ControlledTerm | None = None
    cogatlas: ControlledTerm | None = Field(default=None, alias="cogatlas")


class SimulationResponse(BaseModel):
    scores: Mapping[str, float]
    details: SimulationDetails
    citations: Mapping[str, Sequence[Citation]]
    confidence: Mapping[str, float]
    uncertainty: Mapping[str, float]
    behavioral_tags: Mapping[str, BehavioralTagAnnotation] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Explanation schemas
# ---------------------------------------------------------------------------


class ExplainRequest(BaseModel):
    receptor: str
    direction: str = Field(default="both", pattern="^(both|upstream|downstream)$")
    limit: int = Field(default=20, ge=1, le=100)


class ExplanationEdge(BaseModel):
    direction: str
    edge: GraphEdge
    provenance: Sequence[EvidenceProvenance]


class ExplainResponse(BaseModel):
    receptor: str
    canonical_receptor: str
    kg_weight: float | None
    evidence: float | None
    uncertainty: float | None
    provenance: Sequence[str]
    edges: Sequence[ExplanationEdge]
    causal: CausalDiagnostics | None = None


# ---------------------------------------------------------------------------
# Gap schemas
# ---------------------------------------------------------------------------


class GapRequest(BaseModel):
    focus_nodes: Sequence[str] = Field(..., min_length=2, max_length=50)


class GapDescriptor(BaseModel):
    subject: str
    object: str
    predicate: str | None = None
    reason: str
    embedding_score: float | None = None
    impact_score: float | None = None
    context: Dict[str, Any] = Field(default_factory=dict)
    literature: Sequence[str] = Field(default_factory=list)
    uncertainty: float = Field(default=1.0, ge=0.0, le=1.0)
    counterfactual_summary: str | None = None
    counterfactuals: Sequence[CounterfactualEstimate] = Field(default_factory=list)
    causal: CausalDiagnostics | None = None


class GapResponse(BaseModel):
    items: Sequence[GapDescriptor]


class AssistantAction(str, Enum):
    """Canonical verbs recognised by the assistant aggregation endpoint."""

    EVIDENCE_SEARCH = "evidence_search"
    GRAPH_EXPAND = "graph_expand"
    ATLAS_OVERLAY = "atlas_overlay"
    PREDICT_EFFECTS = "predict_effects"
    SIMULATE = "simulate"
    EXPLAIN = "explain"
    FIND_GAPS = "find_gaps"


class AssistantRequest(BaseModel):
    """Envelope used by clients (e.g. custom GPTs) to call API workflows."""

    action: AssistantAction = Field(..., description="Name of the workflow to execute")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")


class AssistantResponse(BaseModel):
    """Unified response returned by the assistant executor endpoint."""

    action: AssistantAction
    source_endpoint: str = Field(..., description="Underlying REST endpoint that executed the workflow")
    description: str = Field(..., description="Short human-readable summary of the workflow")
    normalized_payload: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)


class AssistantCapability(BaseModel):
    """Declarative description of an assistant workflow."""

    action: AssistantAction
    description: str
    endpoint: str
    payload_schema: Dict[str, Any]


class AssistantCapabilitiesResponse(BaseModel):
    """List of workflows exposed by the assistant endpoints."""

    actions: Sequence[AssistantCapability]


__all__ = [
    "AssistantAction",
    "AssistantCapabilitiesResponse",
    "AssistantCapability",
    "AssistantRequest",
    "AssistantResponse",
    "Citation",
    "CounterfactualEstimate",
    "CausalDiagnostics",
    "ControlledTerm",
    "BehavioralTagAnnotation",
    "ErrorPayload",
    "EvidenceHit",
    "EvidenceProvenance",
    "EvidenceSearchRequest",
    "EvidenceSearchResponse",
    "ExplainRequest",
    "ExplainResponse",
    "ExplanationEdge",
    "GapDescriptor",
    "GapRequest",
    "GapResponse",
    "GraphEdge",
    "GraphExpandRequest",
    "GraphExpandResponse",
    "GraphNode",
    "AtlasOverlayRequest",
    "PredictEffectsRequest",
    "PredictEffectsResponse",
    "ReceptorEffect",
    "ReceptorQuery",
    "ReceptorSpec",
    "SimulationAssumptions",
    "SimulationDetails",
    "SimulationRequest",
    "SimulationResponse",
]
