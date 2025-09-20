"""Pydantic request and response models for the public API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, ConfigDict

from ..graph.models import BiolinkEntity, BiolinkPredicate

Mechanism = str


class Provenance(BaseModel):
    """Metadata describing how a response was assembled."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(..., description="System that produced the payload.")
    notes: Optional[str] = Field(default=None, description="Optional explanation of processing steps.")


class Pagination(BaseModel):
    """Pagination controls shared by multiple endpoints."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    size: int = Field(default=25, ge=1, le=100)


class EvidenceFilters(BaseModel):
    """Filters that can be applied to the evidence search endpoint."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    subject: Optional[str] = Field(default=None, description="CURIE identifier for the subject node.")
    predicate: Optional[BiolinkPredicate] = Field(default=None)
    object_: Optional[str] = Field(default=None, alias="object", description="CURIE identifier for the object node.")
    source: Optional[str] = Field(default=None, description="Evidence source label (e.g. INDRA).")
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class EvidenceRecord(BaseModel):
    """Individual piece of evidence supporting a graph edge."""

    model_config = ConfigDict(extra="forbid")

    source: str
    reference: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    uncertainty: Optional[str] = None
    annotations: Dict[str, Any] = Field(default_factory=dict)


class EvidenceEdge(BaseModel):
    """Serialised edge representation returned by the API."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    subject: str
    predicate: BiolinkPredicate
    object_: str = Field(alias="object")
    relation: Optional[str] = None
    knowledge_level: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[EvidenceRecord] = Field(default_factory=list)


class EvidenceSearchResult(BaseModel):
    """Container bundling an edge with summary statistics."""

    model_config = ConfigDict(extra="forbid")

    edge: EvidenceEdge
    total_evidence: int


class EvidenceSearchRequest(BaseModel):
    """Payload used to query the evidence catalogue."""

    model_config = ConfigDict(extra="forbid")

    filters: EvidenceFilters = Field(default_factory=EvidenceFilters)
    pagination: Pagination = Field(default_factory=Pagination)


class EvidenceSearchResponse(BaseModel):
    """Response returned for evidence search queries."""

    model_config = ConfigDict(extra="forbid")

    results: List[EvidenceSearchResult]
    pagination: Pagination
    filters: EvidenceFilters
    provenance: Provenance
    total: int


class GraphNode(BaseModel):
    """Graph node representation for expansion responses."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: Optional[str] = None
    category: Optional[BiolinkEntity] = None
    description: Optional[str] = None
    provided_by: Optional[str] = None
    synonyms: List[str] = Field(default_factory=list)
    xrefs: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Edge representation for expansion responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    subject: str
    predicate: BiolinkPredicate
    object_: str = Field(alias="object")
    relation: Optional[str] = None
    qualifiers: Dict[str, Any] = Field(default_factory=dict)


class GraphExpandRequest(BaseModel):
    """Request payload for `/graph/expand`."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., description="Seed node identifier to expand around.")
    depth: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=25, ge=1, le=200)
    category_filter: Optional[List[BiolinkEntity]] = Field(default=None, description="Restrict nodes to these categories.")


class GraphExpandResponse(BaseModel):
    """Response returned by `/graph/expand`."""

    model_config = ConfigDict(extra="forbid")

    nodes: List[GraphNode]
    edges: List[GraphEdge]
    provenance: Provenance
    pagination: Pagination


class ReceptorSetting(BaseModel):
    """Input specification for a single receptor."""

    model_config = ConfigDict(extra="forbid")

    occ: float = Field(ge=0.0, le=1.0)
    mech: Mechanism


class SimulationRequest(BaseModel):
    """Payload supplied to the simulation engine."""

    model_config = ConfigDict(extra="forbid")

    receptors: Dict[str, ReceptorSetting] = Field(default_factory=dict)
    acute_1a: bool = False
    adhd: bool = False
    gut_bias: bool = False
    pvt_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class Citation(BaseModel):
    """Literature citation supporting simulated mechanisms."""

    model_config = ConfigDict(extra="forbid")

    title: str
    pmid: Optional[str] = None
    doi: Optional[str] = None


class SimulationResponse(BaseModel):
    """Standard response envelope for the simulation endpoint."""

    model_config = ConfigDict(extra="forbid")

    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, List[Citation]]
    provenance: Provenance


class PredictEffectsRequest(BaseModel):
    """Request body for `/predict/effects`."""

    model_config = ConfigDict(extra="forbid")

    compound_id: str
    simulation: SimulationRequest
    hypothesis: Optional[str] = Field(default=None, description="Optional description of the experimental context.")
    top_n: int = Field(default=3, ge=1, le=6)


class PredictedEffect(BaseModel):
    """Single predicted effect returned by the prediction endpoint."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    score: float
    rationale: str


class PredictEffectsResponse(BaseModel):
    """Response structure for `/predict/effects`."""

    model_config = ConfigDict(extra="forbid")

    compound_id: str
    requested: PredictEffectsRequest
    predicted_effects: List[PredictedEffect]
    provenance: Provenance


class ExplainRequest(BaseModel):
    """Request payload for `/explain`."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    object_: str = Field(alias="object")
    predicate: Optional[BiolinkPredicate] = None
    max_evidence: int = Field(default=5, ge=1, le=25)


class Explanation(BaseModel):
    """Explanation of a relationship derived from the knowledge graph."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    predicate: BiolinkPredicate
    object_: str = Field(alias="object")
    evidence: List[EvidenceRecord]


class ExplainResponse(BaseModel):
    """Response returned by the explanation endpoint."""

    model_config = ConfigDict(extra="forbid")

    explanations: List[Explanation]
    provenance: Provenance


class GapsRequest(BaseModel):
    """Request payload for `/gaps`."""

    model_config = ConfigDict(extra="forbid")

    focus_nodes: List[str] = Field(..., min_length=2, max_length=50)


class GapDescriptor(BaseModel):
    """Description of a detected knowledge gap."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    object_: str = Field(alias="object")
    reason: str


class GapsResponse(BaseModel):
    """Response returned by `/gaps`."""

    model_config = ConfigDict(extra="forbid")

    gaps: List[GapDescriptor]
    provenance: Provenance
    total: int
