"""FastAPI backend for the neuropharm simulation lab.

This service exposes a `/simulate` endpoint that accepts a JSON payload
describing receptor occupancy, pharmacological mechanisms, and
phenotype toggles.  It returns synthetic behavioural scores along with
supporting citations so the frontend can display provenance.  The
current implementation provides a simplified scoring model that can be
swapped for a richer multiscale simulation in future work.

The API also exposes `/` and `/health` endpoints for status checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from .engine.receptors import (
    RECEPTORS,
    get_mechanism_factor,
    get_receptor_weights,
)

# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------

ALLOWED_MECHANISMS = {"agonist", "antagonist", "partial", "inverse"}
API_VERSION = "2025.09.05"
METRICS: Iterable[str] = (
    "drive",
    "apathy",
    "motivation",
    "cognitive_flexibility",
    "anxiety",
    "sleep_quality",
)
SCORE_KEY_MAP = {
    "drive": "DriveInvigoration",
    "apathy": "ApathyBlunting",
    "motivation": "Motivation",
    "cognitive_flexibility": "CognitiveFlexibility",
    "anxiety": "Anxiety",
    "sleep_quality": "SleepQuality",
}


class ReceptorSpec(BaseModel):
    """Specification for a single receptor input from the client."""

    occ: float = Field(..., ge=0.0, le=1.0, description="Receptor occupancy (0.0–1.0).")
    mech: str = Field(..., description="Ligand mechanism (agonist, antagonist, partial, inverse).")

    @validator("mech")
    def _normalise_mechanism(cls, value: str) -> str:
        mechanism = value.strip().lower()
        if mechanism not in ALLOWED_MECHANISMS:
            allowed = ", ".join(sorted(ALLOWED_MECHANISMS))
            raise ValueError(f"Unknown mechanism '{value}'. Choose one of: {allowed}.")
        return mechanism


class SimulationInput(BaseModel):
    """Input payload for the simulation.

    Fields are deliberately flexible to allow future extensions
    (additional neurotransmitters, receptor subtypes, etc.).
    """
    receptors: Dict[str, ReceptorSpec]
    acute_1a: bool = False
    adhd: bool = False
    gut_bias: bool = False
    pvt_weight: float = 0.5


class Citation(BaseModel):
    """Reference supporting a mechanism or receptor effect."""

    title: str
    pmid: str
    doi: str


class SimulationOutput(BaseModel):
    """Return format from the simulation engine."""

    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, List[Citation]]


class EvidenceItem(BaseModel):
    """Structured representation of a mechanistic evidence snippet."""

    id: str
    statement: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    source: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)


class EvidenceSearchResponse(BaseModel):
    """Response payload for the evidence search endpoint."""

    query: str
    results: List[EvidenceItem]


class GraphNode(BaseModel):
    """Node in the neuro-pharmaco causal knowledge graph."""

    id: str
    label: str
    type: str
    tags: List[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    """Edge connecting two graph nodes with supporting evidence identifiers."""

    source: str
    target: str
    relation: str
    evidence: List[str] = Field(default_factory=list)


class GraphExpandRequest(BaseModel):
    """Request payload for graph expansion around a node."""

    node_id: str
    max_depth: int = Field(1, ge=1, le=3)
    include_types: Optional[List[str]] = None


class GraphExpandResponse(BaseModel):
    """Response containing nodes and edges discovered from an expansion request."""

    seed: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class Intervention(BaseModel):
    """Description of an intervention used for predictions."""

    type: str
    name: str
    compound: str
    dose_mg: Optional[float] = None
    schedule: Optional[str] = None
    duration_days: Optional[int] = None


class PredictionContext(BaseModel):
    """Contextual filters for behaviour predictions."""

    species: str
    region_focus: List[str] = Field(default_factory=list)
    behavioral_tags: List[str] = Field(default_factory=list)


class PredictionAssumptions(BaseModel):
    """Model toggles that modify downstream inference."""

    fiveht1a_autoreceptor_desensitization: bool = Field(False, alias="5HT1A_autoreceptor_desensitization")
    trkb_facilitation: bool = Field(False, alias="trkB_facilitation")


class PredictionItem(BaseModel):
    """Single behavioural prediction with supporting rationale."""

    tag: str
    direction: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: List[str]
    key_paths: List[str]
    notes: Optional[str] = None


class UncertaintyReport(BaseModel):
    """Aggregated uncertainty drivers for a prediction run."""

    drivers: List[str]


class SuggestedRead(BaseModel):
    """Metadata for suggested literature to close gaps."""

    source: str
    identifier: str
    title: Optional[str] = None


class GapSuggestion(BaseModel):
    """High-value missing link in the knowledge graph."""

    id: str
    statement: str
    tags: List[str]
    suggested_reads: List[SuggestedRead]


class PredictionResponse(BaseModel):
    """Composite prediction result returned by `/predict/effects`."""

    predictions: List[PredictionItem]
    uncertainty: UncertaintyReport
    gaps: List[GapSuggestion]


class PredictionRequest(BaseModel):
    """Request payload for behavioural predictions."""

    intervention: Intervention
    context: PredictionContext
    assumptions: PredictionAssumptions = PredictionAssumptions()
    receptors: Optional[Dict[str, ReceptorSpec]] = None


class ExplainRequest(BaseModel):
    """Request payload for `/explain` endpoint."""

    intervention: Intervention
    context: PredictionContext
    assumptions: PredictionAssumptions = PredictionAssumptions()
    target_tag: str
    receptors: Optional[Dict[str, ReceptorSpec]] = None


class ExplainResponse(BaseModel):
    """Explanation for a single behavioural tag."""

    tag: str
    rationale: List[str]
    key_paths: List[str]
    citations: Dict[str, List[Citation]]


class GapRequest(BaseModel):
    """Filter payload for `/gaps` endpoint."""

    focus_tags: List[str] = Field(default_factory=list)


class GapResponse(BaseModel):
    """Response payload listing gap suggestions."""

    gaps: List[GapSuggestion]


# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------

app = FastAPI(
    title="Neuropharm Simulation API",
    description=(
        "Simulate serotonergic, dopaminergic and related neurotransmitter systems under "
        "a variety of receptor manipulations. See the project README for payload details."
    ),
)

# Configure CORS
origins = os.environ.get("CORS_ORIGINS", "https://darkfrostx-cmd.github.io").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _status_payload() -> Dict[str, str]:
    return {"status": "ok", "version": API_VERSION}


def _collect_citations(receptor_names: Iterable[str]) -> Dict[str, List[Citation]]:
    """Return structured citations for the provided receptors."""

    citations: Dict[str, List[Citation]] = {}
    for name in receptor_names:
        canon = canonical_receptor_name(name)
        refs = REFERENCES.get(canon)
        if refs:
            citations[canon] = [Citation(**ref) for ref in refs]
    return citations


def _calculate_scores(
    inp: SimulationInput,
    assumption_modifiers: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Run the scoring engine and return scores and raw contributions."""

    contrib: Dict[str, float] = {metric: 0.0 for metric in METRICS}

    for rec_name, spec in inp.receptors.items():
        canon = canonical_receptor_name(rec_name)
        if canon not in RECEPTORS:
            continue
        weights = get_receptor_weights(canon)
        factor = get_mechanism_factor(spec.mech)
        for metric, weight in weights.items():
            contrib[metric] += weight * spec.occ * factor

    if assumption_modifiers:
        for metric, delta in assumption_modifiers.items():
            if metric in contrib:
                contrib[metric] += delta

    if inp.adhd:
        contrib["drive"] -= 0.3
        contrib["motivation"] -= 0.2
    if inp.gut_bias:
        for metric in METRICS:
            if contrib[metric] < 0:
                contrib[metric] *= 0.9
    if inp.acute_1a:
        for metric in METRICS:
            contrib[metric] *= 0.75

    contrib_scale = 1.0 - (inp.pvt_weight * 0.2)
    for metric in METRICS:
        contrib[metric] *= contrib_scale

    scores: Dict[str, float] = {}
    for metric in METRICS:
        base = 50.0
        change = 20.0 * contrib[metric]
        value = base + change
        if metric == "apathy":
            value = 100.0 - value
        scores_name = SCORE_KEY_MAP[metric]
        scores[scores_name] = max(0.0, min(100.0, value))

    return scores, contrib


def _assumption_modifiers(assumptions: PredictionAssumptions) -> Dict[str, float]:
    """Translate prediction assumptions into contribution tweaks."""

    modifiers: Dict[str, float] = {}
    if assumptions.fiveht1a_autoreceptor_desensitization:
        modifiers["drive"] = modifiers.get("drive", 0.0) + 0.12
        modifiers["motivation"] = modifiers.get("motivation", 0.0) + 0.15
        modifiers["apathy"] = modifiers.get("apathy", 0.0) - 0.1
    if assumptions.trkb_facilitation:
        modifiers["motivation"] = modifiers.get("motivation", 0.0) + 0.12
        modifiers["cognitive_flexibility"] = modifiers.get("cognitive_flexibility", 0.0) + 0.12
        modifiers["anxiety"] = modifiers.get("anxiety", 0.0) - 0.05
    return modifiers


def _build_simulation_from_prediction(
    req: PredictionRequest,
) -> Tuple[SimulationInput, Dict[str, float]]:
    """Construct a `SimulationInput` and modifiers for a prediction request."""

    base = DEFAULT_INTERVENTIONS.get(req.intervention.compound.lower(), {})
    receptor_payload: Dict[str, Any] = dict(base.get("receptors", {}))
    if req.receptors:
        for name, spec in req.receptors.items():
            receptor_payload[name] = spec.dict()

    modifiers = base.get("modifiers", {})
    sim_input = SimulationInput(
        receptors=receptor_payload,
        adhd=modifiers.get("adhd", False),
        acute_1a=modifiers.get("acute_1a", False),
        gut_bias=modifiers.get("gut_bias", False),
        pvt_weight=modifiers.get("pvt_weight", 0.5),
    )

    return sim_input, _assumption_modifiers(req.assumptions)


def _confidence_from_delta(delta: float, assumptions: PredictionAssumptions) -> float:
    """Convert a metric delta into an interpretable confidence score."""

    base = 0.45 + min(0.4, abs(delta) / 30.0)
    if assumptions.fiveht1a_autoreceptor_desensitization:
        base += 0.05
    if assumptions.trkb_facilitation:
        base += 0.05
    return round(min(0.95, max(0.3, base)), 2)


def _direction_from_delta(delta: float, positive: str, negative: str) -> str:
    """Return a qualitative direction label based on delta magnitude."""

    if abs(delta) < 3.0:
        return "mixed"
    return positive if delta > 0 else negative


def _aggregate_uncertainty(tags: Sequence[str]) -> List[str]:
    seen: List[str] = []
    for tag in tags:
        for item in PREDICTION_PLAYBOOK.get(tag, {}).get("uncertainty", []):
            if item not in seen:
                seen.append(item)
    return seen


def _resolve_gaps(gap_ids: Sequence[str]) -> List[GapSuggestion]:
    results: List[GapSuggestion] = []
    seen: set[str] = set()
    for gid in gap_ids:
        if gid in seen:
            continue
        seen.add(gid)
        data = GAP_LIBRARY.get(gid)
        if not data:
            continue
        reads = [SuggestedRead(**item) for item in data.get("suggested_reads", [])]
        results.append(
            GapSuggestion(
                id=gid,
                statement=data["statement"],
                tags=data.get("tags", []),
                suggested_reads=reads,
            )
        )
    return results


def _build_prediction_for_tag(
    tag: str,
    scores: Dict[str, float],
    assumptions: PredictionAssumptions,
) -> Optional[PredictionItem]:
    playbook = PREDICTION_PLAYBOOK.get(tag)
    if not playbook:
        return None

    metric = playbook["metric"]
    score_key = SCORE_KEY_MAP.get(metric)
    if not score_key:
        return None
    metric_score = scores.get(score_key, 50.0)
    delta = metric_score - 50.0
    direction = _direction_from_delta(delta, playbook["positive_direction"], playbook["negative_direction"])
    confidence = _confidence_from_delta(delta, assumptions)

    return PredictionItem(
        tag=tag,
        direction=direction,
        confidence=confidence,
        rationale=playbook["rationale"],
        key_paths=playbook["paths"],
        notes=playbook.get("notes"),
    )


def _execute_prediction(
    req: PredictionRequest,
) -> Tuple[SimulationInput, Dict[str, float], Dict[str, float], Dict[str, List[Citation]]]:
    sim_input, modifiers = _build_simulation_from_prediction(req)
    scores, contrib = _calculate_scores(sim_input, modifiers)
    citations = _collect_citations(sim_input.receptors.keys())
    return sim_input, scores, contrib, citations


@app.get("/")
def read_root() -> Dict[str, str]:
    """Basic health check for uptime monitors."""

    return _status_payload()


@app.get("/health")
def health() -> Dict[str, str]:
    """Compatibility endpoint mirroring the root status payload."""

    return _status_payload()


def canonical_receptor_name(name: str) -> str:
    """Normalise receptor identifiers to the canonical form used in ``RECEPTORS``."""

    raw = name.strip().upper()
    if raw in RECEPTORS:
        return raw

    compact = raw.replace(" ", "").replace("_", "")
    if compact in RECEPTORS:
        return compact

    if compact.startswith("5HT"):
        compact = "5-HT" + compact[3:]
    compact = compact.replace("--", "-")
    if compact in RECEPTORS:
        return compact

    compact_no_dash = compact.replace("-", "")
    for canon in RECEPTORS:
        if compact_no_dash == canon.replace("-", ""):
            return canon

    return raw


def _load_references() -> Dict[str, List[Dict[str, str]]]:
    refs_path = Path(__file__).with_name("refs.json")
    if not refs_path.exists():
        return {}
    with refs_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {key.upper(): value for key, value in data.items()}


REFERENCES = _load_references()

EVIDENCE_INDEX: List[Dict[str, Any]] = [
    {
        "id": "E-5HT1A-CHRONIC",
        "statement": "Chronic SSRI exposure desensitises dorsal raphe 5-HT1A autoreceptors, increasing forebrain serotonin tone.",
        "pmid": "1395583",
        "doi": "10.1038/1395583",
        "source": "Nature",
        "confidence": 0.82,
        "tags": ["5-HT1A", "autoreceptor", "chronic", "SSRI"],
    },
    {
        "id": "E-TRKB-BINDING",
        "statement": "Classical and rapid-acting antidepressants facilitate TrkB signalling and synaptic plasticity.",
        "pmid": "33606976",
        "doi": "10.1523/JNEUROSCI.1751-19.2019",
        "source": "Cell Reports",
        "confidence": 0.78,
        "tags": ["TrkB", "plasticity", "antidepressant"],
    },
    {
        "id": "E-ALPHA2A-HCN",
        "statement": "α2A adrenergic receptor agonism suppresses cAMP, closes HCN channels and stabilises prefrontal networks.",
        "pmid": "17448997",
        "doi": "10.1038/nn1908",
        "source": "Nature Neuroscience",
        "confidence": 0.75,
        "tags": ["alpha2A", "HCN", "PFC", "executive"],
    },
    {
        "id": "E-ACH-BLA",
        "statement": "Cue-predictive reward signals trigger acetylcholine release in the basolateral amygdala to encode salience.",
        "pmid": "33028649",
        "doi": "10.1016/j.neuron.2020.09.020",
        "source": "Neuron",
        "confidence": 0.7,
        "tags": ["acetylcholine", "amygdala", "salience"],
    },
]

GRAPH_NODES: Dict[str, Dict[str, Any]] = {
    "fluoxetine": {"label": "Fluoxetine", "type": "drug", "tags": ["SSRI"]},
    "sert": {"label": "SERT", "type": "target", "tags": ["transporter"]},
    "5-ht1a_auto": {"label": "5-HT1A Autoreceptor", "type": "receptor", "tags": ["tonic", "raphe"]},
    "5-ht2c": {"label": "5-HT2C Receptor", "type": "receptor", "tags": ["phasic", "gaba"]},
    "trkb": {"label": "TrkB", "type": "receptor", "tags": ["plasticity"]},
    "bndf": {"label": "BDNF", "type": "ligand", "tags": ["neurotrophin"]},
    "mesolimbic_dopamine": {"label": "Mesolimbic DA", "type": "circuit", "tags": ["VTA", "NAc"]},
    "social_affiliation": {"label": "Social Affiliation", "type": "behaviour", "tags": ["RDoC", "social"]},
    "exploratory_behavior": {"label": "Exploratory Behaviour", "type": "behaviour", "tags": ["RDoC", "motivation"]},
}

GRAPH_EDGES: List[Dict[str, Any]] = [
    {"source": "fluoxetine", "target": "sert", "relation": "inhibits", "evidence": ["E-5HT1A-CHRONIC"]},
    {"source": "sert", "target": "5-ht1a_auto", "relation": "reduces_gain", "evidence": ["E-5HT1A-CHRONIC"]},
    {"source": "fluoxetine", "target": "5-ht2c", "relation": "antagonises", "evidence": ["E-5HT1A-CHRONIC"]},
    {"source": "fluoxetine", "target": "trkb", "relation": "facilitates", "evidence": ["E-TRKB-BINDING"]},
    {"source": "trkb", "target": "bndf", "relation": "activates", "evidence": ["E-TRKB-BINDING"]},
    {"source": "bndf", "target": "mesolimbic_dopamine", "relation": "enhances_plasticity", "evidence": ["E-TRKB-BINDING"]},
    {"source": "mesolimbic_dopamine", "target": "social_affiliation", "relation": "supports", "evidence": ["E-ACH-BLA"]},
    {"source": "mesolimbic_dopamine", "target": "exploratory_behavior", "relation": "modulates", "evidence": ["E-ACH-BLA"]},
]

DEFAULT_INTERVENTIONS: Dict[str, Dict[str, Any]] = {
    "fluoxetine": {
        "receptors": {
            "5-HT2C": {"occ": 0.35, "mech": "antagonist"},
            "5-HT1B": {"occ": 0.2, "mech": "partial"},
            "5-HT1A": {"occ": 0.25, "mech": "agonist"},
            "5-HT7": {"occ": 0.18, "mech": "antagonist"},
            "MT2": {"occ": 0.12, "mech": "agonist"},
        },
        "modifiers": {"adhd": False, "acute_1a": False, "gut_bias": False, "pvt_weight": 0.55},
    },
    "ketamine": {
        "receptors": {
            "5-HT7": {"occ": 0.25, "mech": "agonist"},
            "5-HT1A": {"occ": 0.2, "mech": "agonist"},
        },
        "modifiers": {"adhd": False, "acute_1a": False, "gut_bias": False, "pvt_weight": 0.45},
    },
}

PREDICTION_PLAYBOOK: Dict[str, Dict[str, Any]] = {
    "anhedonia": {
        "metric": "motivation",
        "positive_direction": "down",
        "negative_direction": "up",
        "rationale": [
            "↑5-HT tone via DRN autoreceptor desensitisation over weeks",
            "↑BDNF/TrkB signalling enables AMPA potentiation and synaptogenesis",
        ],
        "paths": [
            "fluoxetine -> SERT block -> 5-HT1A_auto (↓gain) -> 5-HT tone ↑ -> mesolimbic DA phasic ↑",
            "fluoxetine -> TrkB facilitation -> BDNF ↑ -> NAc synaptogenesis",
        ],
        "notes": "Magnitude depends on chronic dosing and downstream plasticity consolidation.",
        "uncertainty": ["TrkB binding strength in vivo", "Regional SSRI concentrations"],
        "gaps": ["GAP-5HT2C-PHASIC"],
    },
    "exploratory-behavior": {
        "metric": "drive",
        "positive_direction": "up",
        "negative_direction": "down",
        "rationale": [
            "5-HT2C antagonism disinhibits VTA dopamine bursts",
            "α2A-like network stabilisation in PFC biases towards focused, lower exploration",
        ],
        "paths": [
            "fluoxetine -> 5-HT2C antagonism -> VTA GABA ↓ -> DA burst probability ↑",
            "fluoxetine -> cortical 5-HT1A tone -> executive control stabilisation",
        ],
        "notes": "Balance of mesolimbic drive vs. prefrontal control yields mixed exploratory changes.",
        "uncertainty": ["Context-dependent PFC gating", "Species differences in 5-HT2C expression"],
        "gaps": ["GAP-ALPHA2C-SOCIAL"],
    },
    "social-affiliation": {
        "metric": "cognitive_flexibility",
        "positive_direction": "up",
        "negative_direction": "down",
        "rationale": [
            "TrkB-driven plasticity strengthens mesolimbic social salience coding",
            "MT2 support of circadian alignment stabilises social approach cues",
        ],
        "paths": [
            "fluoxetine -> TrkB facilitation -> BDNF ↑ -> Mesolimbic DA plasticity",
            "fluoxetine -> MT2 agonism -> circadian synchrony -> social rhythm entrainment",
        ],
        "notes": "Social affiliation improvements lag acute mood lift due to circuit-level remodelling.",
        "uncertainty": ["Inter-individual BDNF polymorphisms", "Circadian adherence"],
        "gaps": ["GAP-BLA-ACH-SOCIAL"],
    },
}

GAP_LIBRARY: Dict[str, Dict[str, Any]] = {
    "GAP-5HT2C-PHASIC": {
        "statement": "Human data on 5-HT2C modulation of dopamine phasic bursts under chronic SSRI remain sparse.",
        "tags": ["exploratory-behavior", "anhedonia"],
        "suggested_reads": [
            {"source": "OpenAlex", "identifier": "W1234567890", "title": "5-HT2C regulation of mesolimbic dopamine"},
            {"source": "Semantic Scholar", "identifier": "CorpusID:24567890", "title": "Serotonin-dopamine interplay in reward"},
        ],
    },
    "GAP-ALPHA2C-SOCIAL": {
        "statement": "Clarify alpha2C contributions to striatal social reinforcement learning in humans.",
        "tags": ["social-affiliation", "exploratory-behavior"],
        "suggested_reads": [
            {"source": "OpenAlex", "identifier": "W9081726354", "title": "Alpha2C antagonists and motivational circuits"},
        ],
    },
    "GAP-BLA-ACH-SOCIAL": {
        "statement": "Need longitudinal evidence linking amygdala cholinergic bursts to social affiliation outcomes post-SSRI.",
        "tags": ["social-affiliation"],
        "suggested_reads": [
            {"source": "OpenAlex", "identifier": "W5647382910", "title": "Amygdala ACh signalling in social behaviour"},
        ],
    },
}

@app.post("/simulate", response_model=SimulationOutput)
def simulate(inp: SimulationInput) -> SimulationOutput:
    """Run a single simulation with the provided input.

    This function currently implements a highly simplified scoring
    algorithm. It computes phasic dopamine drive based on 5‑HT2C and
    5‑HT1B occupancy, modulates it with ADHD state and gut-bias flags,
    and then maps the result into overall "Drive" and "Apathy" scores.


Parameters
    ----------
    inp : SimulationInput
        The payload specifying receptor occupancies and modifiers.

    Returns
    -------
    SimulationOutput
        A dictionary containing high‑level scores, intermediate details
        and citations underpinning the mechanisms used.
    """
    scores, contrib = _calculate_scores(inp)
    citations = _collect_citations(inp.receptors.keys())
    details = {"raw_contributions": contrib, "final_scores": scores}
    return SimulationOutput(scores=scores, details=details, citations=citations)


@app.get("/evidence/search", response_model=EvidenceSearchResponse)
def evidence_search(query: str = Query(..., min_length=1, description="Mechanism or receptor search string.")) -> EvidenceSearchResponse:
    """Return mechanistic evidence snippets that match the query."""

    lowered = query.lower()
    results: List[EvidenceItem] = []
    for record in EVIDENCE_INDEX:
        haystack = " ".join([
            record["statement"],
            " ".join(record.get("tags", [])),
            record.get("source", ""),
        ]).lower()
        if lowered in haystack:
            results.append(EvidenceItem(**record))
    if not results:
        # fallback: return top two items ranked by overlap of query tokens
        tokens = [token for token in lowered.split() if token]
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for record in EVIDENCE_INDEX:
            score = sum(1 for token in tokens if token in record["statement"].lower())
            scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        for _, record in scored[:2]:
            results.append(EvidenceItem(**record))

    return EvidenceSearchResponse(query=query, results=results)


@app.post("/graph/expand", response_model=GraphExpandResponse)
def graph_expand(req: GraphExpandRequest) -> GraphExpandResponse:
    """Expand the knowledge graph around a node up to a limited depth."""

    seed = req.node_id.lower()
    if seed not in GRAPH_NODES:
        raise HTTPException(status_code=404, detail=f"Unknown node '{req.node_id}'.")

    include_types = set(t.lower() for t in req.include_types) if req.include_types else None

    collected: set[str] = {seed}
    queue: List[Tuple[str, int]] = [(seed, 0)]

    while queue:
        node_id, depth = queue.pop(0)
        if depth >= req.max_depth:
            continue
        for edge in GRAPH_EDGES:
            neighbours: List[str] = []
            if edge["source"] == node_id:
                neighbours.append(edge["target"])
            if edge["target"] == node_id:
                neighbours.append(edge["source"])
            for neighbour in neighbours:
                if neighbour not in GRAPH_NODES:
                    continue
                node_type = GRAPH_NODES[neighbour]["type"].lower()
                if include_types and node_type not in include_types:
                    continue
                if neighbour not in collected:
                    collected.add(neighbour)
                    queue.append((neighbour, depth + 1))

    node_models = [
        GraphNode(id=node_id, label=GRAPH_NODES[node_id]["label"], type=GRAPH_NODES[node_id]["type"], tags=GRAPH_NODES[node_id].get("tags", []))
        for node_id in collected
    ]

    edge_models: List[GraphEdge] = []
    seen_edges: set[Tuple[str, str, str]] = set()
    for edge in GRAPH_EDGES:
        if edge["source"] in collected and edge["target"] in collected:
            key = (edge["source"], edge["target"], edge["relation"])
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_models.append(
                GraphEdge(
                    source=edge["source"],
                    target=edge["target"],
                    relation=edge["relation"],
                    evidence=edge.get("evidence", []),
                )
            )

    node_models.sort(key=lambda node: node.id)

    return GraphExpandResponse(seed=req.node_id, nodes=node_models, edges=edge_models)


@app.post("/predict/effects", response_model=PredictionResponse)
def predict_effects(req: PredictionRequest) -> PredictionResponse:
    """Predict behavioural tag directions for a requested intervention."""

    _, scores, _, _ = _execute_prediction(req)
    requested_tags = req.context.behavioral_tags or list(PREDICTION_PLAYBOOK.keys())
    predictions: List[PredictionItem] = []
    for tag in requested_tags:
        item = _build_prediction_for_tag(tag, scores, req.assumptions)
        if item:
            predictions.append(item)

    uncertainty = UncertaintyReport(drivers=_aggregate_uncertainty([item.tag for item in predictions]))
    gap_ids: List[str] = []
    for item in predictions:
        gap_ids.extend(PREDICTION_PLAYBOOK.get(item.tag, {}).get("gaps", []))
    gaps = _resolve_gaps(gap_ids)

    return PredictionResponse(predictions=predictions, uncertainty=uncertainty, gaps=gaps)


@app.post("/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest) -> ExplainResponse:
    """Return causal paths and citations supporting a behavioural prediction."""

    prediction_req = PredictionRequest(
        intervention=req.intervention,
        context=req.context,
        assumptions=req.assumptions,
        receptors=req.receptors,
    )
    _, scores, _, citations = _execute_prediction(prediction_req)
    item = _build_prediction_for_tag(req.target_tag, scores, req.assumptions)
    if not item:
        raise HTTPException(status_code=404, detail=f"Unknown behavioural tag '{req.target_tag}'.")

    return ExplainResponse(tag=req.target_tag, rationale=item.rationale, key_paths=item.key_paths, citations=citations)


@app.post("/gaps", response_model=GapResponse)
def gaps(req: GapRequest) -> GapResponse:
    """Return knowledge gaps prioritised for the provided focus tags."""

    if req.focus_tags:
        gap_ids: List[str] = []
        for tag in req.focus_tags:
            gap_ids.extend(PREDICTION_PLAYBOOK.get(tag, {}).get("gaps", []))
        suggestions = _resolve_gaps(gap_ids)
    else:
        suggestions = _resolve_gaps(list(GAP_LIBRARY.keys()))

    return GapResponse(gaps=suggestions)
