"""Pydantic schemas used by the public API surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Sequence, Literal

from pydantic import BaseModel, Field

from ..graph.models import BiolinkPredicate, Edge, Evidence, Node


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


class SimulationRequest(BaseModel):
    receptors: Mapping[str, ReceptorSpec]
    acute_1a: bool = False
    dosing: Literal["acute", "chronic"] = "chronic"
    adhd: bool = False
    gut_bias: bool = False
    pvt_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class Citation(BaseModel):
    title: str
    pmid: str | None = None
    doi: str | None = None


class SimulationDetails(BaseModel):
    timepoints: Sequence[float]
    trajectories: Mapping[str, Sequence[float]]
    modules: Dict[str, Any]
    receptor_context: Mapping[str, Dict[str, Any]]


class SimulationResponse(BaseModel):
    scores: Mapping[str, float]
    details: SimulationDetails
    citations: Mapping[str, Sequence[Citation]]
    confidence: Mapping[str, float]
    uncertainty: Mapping[str, float]


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


# ---------------------------------------------------------------------------
# Gap schemas
# ---------------------------------------------------------------------------


class GapRequest(BaseModel):
    focus_nodes: Sequence[str] = Field(..., min_length=2, max_length=50)


class GapDescriptor(BaseModel):
    subject: str
    object: str
    reason: str
    uncertainty: float = Field(default=1.0, ge=0.0, le=1.0)


class GapResponse(BaseModel):
    items: Sequence[GapDescriptor]


__all__ = [
    "Citation",
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
    "PredictEffectsRequest",
    "PredictEffectsResponse",
    "ReceptorEffect",
    "ReceptorQuery",
    "ReceptorSpec",
    "SimulationDetails",
    "SimulationRequest",
    "SimulationResponse",
]
