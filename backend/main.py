"""
FastAPI backend for the neuropharm simulation lab.

This service exposes a `/simulate` endpoint that accepts a JSON
payload describing the current receptor occupancy, acute/chronic flags,
phenotype modifiers (such as ADHD), gut-bias toggles, and other
parameters. It returns computed scores for motivational drive, apathy
blunting, and other high‑level readouts.  The current implementation
provides a simple placeholder model to demonstrate the API and wiring;
future work should extend this file with a full mechanistic model of
serotonin, dopamine, glutamate, histamine, and other systems across
brain regions.

The API also exposes a root `/` endpoint for a basic health check.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from fastapi.middleware.cors import CORSMiddleware


import numpy as np
import os
import json

from .engine.receptors import get_receptor_weights, get_mechanism_factor, RECEPTORS

# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------

class ReceptorSpec(BaseModel):
    """Specification for a single receptor.

    Attributes
    ----------
    occ : float
        Fractional occupancy of the receptor (0.0–1.0).
    mech : str
        Mechanism of the ligand ("agonist", "antagonist", "partial", or
        "inverse").  Future versions may support additional values.
    """
    occ: float
    mech: str


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
    """Reference supporting a receptor mechanism."""

    title: str
    pmid: Optional[str] = None
    doi: Optional[str] = None


class SimulationOutput(BaseModel):
    """Return format from the simulation engine.

    `scores` contains high‑level behavioural metrics normalised to 0–100.
    `details` includes intermediate values (e.g. computed dopamine phasic
    drive) that may be useful for debugging or future UI visualisations.
    `citations` returns structured references supporting the mechanisms
    involved in generating the result.
    """

    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, List[Citation]]


def canonical_receptor_name(name: str) -> str:
    """Normalise a receptor name to the canonical key used by the engine."""

    stripped = name.strip()
    if not stripped:
        return stripped

    normalised = stripped.upper().replace(" ", "").replace("_", "-")

    if normalised.startswith("5HT"):
        suffix = normalised[3:].lstrip("-")
        return f"5-HT{suffix}"

    if normalised.startswith("5-HT"):
        suffix = normalised[4:].lstrip("-")
        return f"5-HT{suffix}"

    return normalised


def load_references() -> Dict[str, List[Citation]]:
    """Load structured receptor citations from ``refs.json`` if present."""

    refs_path = os.path.join(os.path.dirname(__file__), "refs.json")
    try:
        with open(refs_path, "r", encoding="utf-8") as f:
            refs_data = json.load(f)
    except FileNotFoundError:
        return {}

    references: Dict[str, List[Citation]] = {}
    for raw_name, entries in refs_data.items():
        canon_name = canonical_receptor_name(raw_name)
        parsed_entries: List[Citation] = []
        for entry in entries:
            if isinstance(entry, dict):
                parsed_entries.append(Citation(**entry))
            elif isinstance(entry, str):
                parsed_entries.append(Citation(title=entry))
        if parsed_entries:
            references.setdefault(canon_name, []).extend(parsed_entries)
    return references


REFERENCES: Dict[str, List[Citation]] = load_references()


# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------

app = FastAPI(
    title="Neuropharm Simulation API",
    description=(
        "Simulate serotonergic, dopaminergic and other\n"
        "neurotransmitter systems under a variety of\n"
        "receptor manipulations.  See the README for\n"
        "details on the expected payload format."
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


@app.get("/")
def read_root():
    """Health check endpoint.

    Returns a basic status message so that clients can confirm the API is
    running.
    """
    return {"status": "ok", "version": "2025.09.05"}



@app.get("/health")
def health():
    return {"status": "ok", "version": "2025.09.05"}


@app.post("/simulate", response_model=SimulationOutput)
def simulate(inp: SimulationInput) -> SimulationOutput:
    """Run a single simulation with the provided input payload."""

    metrics = [
        "drive",
        "apathy",
        "motivation",
        "cognitive_flexibility",
        "anxiety",
        "sleep_quality",
    ]
    contrib: Dict[str, float] = {m: 0.0 for m in metrics}

    for rec_name, spec in inp.receptors.items():
        canon = canonical_receptor_name(rec_name)
        if canon not in RECEPTORS:
            continue
        weights = get_receptor_weights(canon)
        factor = get_mechanism_factor(spec.mech)
        for metric, weight in weights.items():
            contrib[metric] += weight * spec.occ * factor

    if inp.adhd:
        contrib["drive"] -= 0.3
        contrib["motivation"] -= 0.2
    if inp.gut_bias:
        for metric in metrics:
            if contrib[metric] < 0:
                contrib[metric] *= 0.9
    if inp.acute_1a:
        for metric in metrics:
            contrib[metric] *= 0.75

    contrib_scale = 1.0 - (inp.pvt_weight * 0.2)
    for metric in metrics:
        contrib[metric] *= contrib_scale

    scores: Dict[str, float] = {}
    for metric in metrics:
        base = 50.0
        change = 20.0 * contrib[metric]
        value = base + change
        if metric == "apathy":
            value = 100.0 - value
        score_name = {
            "drive": "DriveInvigoration",
            "apathy": "ApathyBlunting",
            "motivation": "Motivation",
            "cognitive_flexibility": "CognitiveFlexibility",
            "anxiety": "Anxiety",
            "sleep_quality": "SleepQuality",
        }[metric]
        scores[score_name] = max(0.0, min(100.0, value))

    citations: Dict[str, List[Citation]] = {}
    for rec_name in inp.receptors.keys():
        canon = canonical_receptor_name(rec_name)
        if canon in REFERENCES:
            citations[canon] = [
                Citation.model_validate(ref.model_dump()) for ref in REFERENCES[canon]
            ]

    details = {
        "raw_contributions": contrib,
        "final_scores": scores,
    }

    return SimulationOutput(scores=scores, details=details, citations=citations)
