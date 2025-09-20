from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from ..graph.models import BiolinkEntity, BiolinkPredicate

Mechanism = Literal["agonist", "antagonist", "partial", "inverse"]


class Citation(BaseModel):
    """Reference supporting a mechanism or receptor effect."""

    title: str
    pmid: Optional[str] = None
    doi: Optional[str] = None


class EvidenceDetail(BaseModel):
    """Evidence record associated with an edge."""

    source: str
    reference: Optional[str] = None
    confidence: Optional[float] = None
    uncertainty: Optional[str] = None
    annotations: Dict[str, Any] = Field(default_factory=dict)


class EdgeSummary(BaseModel):
    """Serializable representation of an edge and its evidence."""

    model_config = ConfigDict(use_enum_values=True)

    subject: str
    predicate: BiolinkPredicate
    object: str
    relation: str
    knowledge_level: Optional[str] = None
    confidence: Optional[float] = None
    publications: List[str] = Field(default_factory=list)
    evidence: List[EvidenceDetail] = Field(default_factory=list)
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class NodeSummary(BaseModel):
    """Serializable representation of a graph node."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    name: str
    category: BiolinkEntity = BiolinkEntity.NAMED_THING
    description: Optional[str] = None
    provided_by: Optional[str] = None
    synonyms: List[str] = Field(default_factory=list)
    xrefs: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class EvidenceSearchRequest(BaseModel):
    """Filter and pagination payload for evidence search."""

    model_config = ConfigDict(use_enum_values=True)

    subject: Optional[str] = None
    predicate: Optional[BiolinkPredicate] = None
    object: Optional[str] = None
    page: PositiveInt = Field(default=1, description="1-indexed page number")
    page_size: PositiveInt = Field(
        default=25,
        le=100,
        description="Maximum number of records to return per page (<=100).",
    )


class PaginatedEvidenceResponse(BaseModel):
    """Paginated evidence query response."""

    results: List[EdgeSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class GraphExpandRequest(BaseModel):
    """Payload for expanding a neighbourhood around a node."""

    node_id: str = Field(description="Seed node identifier (CURIE or URI).")
    depth: PositiveInt = Field(default=1, le=3, description="Traversal depth (max 3).")
    limit: PositiveInt = Field(default=25, le=200, description="Maximum number of nodes to return.")


class GraphFragmentResponse(BaseModel):
    """Response containing expanded graph fragment."""

    nodes: List[NodeSummary] = Field(default_factory=list)
    edges: List[EdgeSummary] = Field(default_factory=list)


class ReceptorSpec(BaseModel):
    """Specification for a single receptor in prediction/simulation payloads."""

    occ: float = Field(ge=0.0, le=1.0, description="Fractional receptor occupancy (0-1).")
    mech: Mechanism


class BaseSimulationRequest(BaseModel):
    """Common fields shared by prediction/simulation payloads."""

    receptors: Dict[str, ReceptorSpec]
    acute_1a: bool = False
    dosing: Literal["acute", "chronic"] = "chronic"
    adhd: bool = False
    gut_bias: bool = False
    pvt_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class PredictEffectsRequest(BaseSimulationRequest):
    """Request body for /predict/effects."""


class SimulationRequest(BaseSimulationRequest):
    """Request body for /simulate."""


class ExplainRequest(BaseSimulationRequest):
    """Request body for /explain."""

    metric: Optional[str] = Field(
        default=None,
        description="Optional metric to focus on (e.g. 'Motivation' or 'DriveInvigoration').",
    )


class SimulationDetails(BaseModel):
    """Structured details returned by the simulation engine."""

    timepoints: List[float] = Field(default_factory=list)
    trajectories: Dict[str, List[float]] = Field(default_factory=dict)
    modules: Dict[str, Any] = Field(default_factory=dict)
    ignored_receptors: List[str] = Field(default_factory=list)


class SimulationResponse(BaseModel):
    """Response payload for /simulate."""

    scores: Dict[str, float]
    details: SimulationDetails
    citations: Dict[str, List[Citation]] = Field(default_factory=dict)
    confidence: Dict[str, float]


class ReceptorContribution(BaseModel):
    """Per-receptor contribution summary returned by /predict/effects."""

    receptor: str
    canonical_receptor: str
    mechanism: Mechanism
    occupancy: float = Field(ge=0.0, le=1.0)
    score_delta: Dict[str, float] = Field(
        default_factory=dict,
        description="Score delta contributions in behavioural metric units.",
    )
    evidence: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    citations: List[Citation] = Field(default_factory=list)


class PredictEffectsResponse(BaseModel):
    """Response payload for /predict/effects."""

    scores: Dict[str, float]
    contributions: List[ReceptorContribution] = Field(default_factory=list)
    uncertainty: Dict[str, float]
    modifiers: Dict[str, float] = Field(default_factory=dict)
    ignored_targets: List[str] = Field(default_factory=list)


class ExplanationDriver(BaseModel):
    """Driver entry surfaced by the /explain endpoint."""

    receptor: str
    canonical_receptor: str
    mechanism: Mechanism
    score_delta: float
    confidence: float = Field(ge=0.0, le=1.0)
    citations: List[Citation] = Field(default_factory=list)


class ExplainResponse(BaseModel):
    """Response payload for /explain."""

    metric: str
    predicted_score: float
    summary: str
    drivers: List[ExplanationDriver] = Field(default_factory=list)
    uncertainty: float = Field(ge=0.0, le=1.0)
    modifiers: Dict[str, float] = Field(default_factory=dict)
    ignored_targets: List[str] = Field(default_factory=list)


class GraphGapRequest(BaseModel):
    """Payload describing the focus nodes for /gaps."""

    focus: List[str] = Field(..., min_length=1, max_length=100)


class GraphGapItem(BaseModel):
    """Single gap description."""

    subject: str
    object: str
    reason: str


class GraphGapResponse(BaseModel):
    """Response payload for /gaps."""

    gaps: List[GraphGapItem] = Field(default_factory=list)
