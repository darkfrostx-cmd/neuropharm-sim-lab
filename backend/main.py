"""
FastAPI backend for the neuropharm simulation lab.

This service exposes a `/simulate` endpoint that accepts a JSON
payload describing the current receptor occupancy, acute/chronic flags,
phenotype modifiers (such as ADHD), gut-bias toggles, and other
parameters. It returns computed scores for motivational drive, apathy
blunting, and other high-level readouts.  The current implementation
provides a simple placeholder model to demonstrate the API and wiring;
future work should extend this file with a full mechanistic model of
serotonin, dopamine, glutamate, histamine, and other systems across
brain regions.

The API also exposes a root `/` endpoint for a basic health check.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .engine.receptors import (
    RECEPTORS,
    get_mechanism_factor,
    get_receptor_weights,
)


# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------


class ReceptorSpec(BaseModel):
    """Specification for a single receptor."""

    occ: float
    mech: str


class SimulationInput(BaseModel):
    """Input payload for the simulation."""

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
    """Return format from the simulation engine."""

    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, List[Citation]]


# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------


app = FastAPI(
    title="Neuropharm Simulation API",
    description=(
        "Simulate serotonergic, dopaminergic and other\n"
        "                           neurotransmitter systems under a variety of\n"
        "                           receptor manipulations.  See the README for\n"
        "                           details on the expected payload format."
    ),
)

# Configure CORS
origins = os.environ.get(
    "CORS_ORIGINS", "https://darkfrostx-cmd.github.io"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root() -> Dict[str, str]:
    """Health check endpoint."""

    return {"status": "ok", "version": "2025.09.05"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": "2025.09.05"}


@app.post("/simulate", response_model=SimulationOutput)
def simulate(inp: SimulationInput) -> SimulationOutput:
    """Run a single simulation with the provided input."""

    def canonical_receptor_name(name: str) -> str:
        if name in RECEPTORS:
            return name
        # Normalise names like "5HT2C" → "5-HT2C" and "5ht1a" → "5-HT1A"
        name_upper = name.upper().replace("HT", "-HT")
        return name_upper

    refs_path = os.path.join(os.path.dirname(__file__), "refs.json")
    try:
        with open(refs_path, "r", encoding="utf-8") as f:
            refs_raw = json.load(f)
    except FileNotFoundError:
        refs_raw = {}

    refs: Dict[str, List[Citation]] = {}
    for rec_name, entries in refs_raw.items():
        canon_name = canonical_receptor_name(rec_name)
        refs[canon_name] = [Citation(**entry) for entry in entries]

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
        score_key = {
            "drive": "DriveInvigoration",
            "apathy": "ApathyBlunting",
            "motivation": "Motivation",
            "cognitive_flexibility": "CognitiveFlexibility",
            "anxiety": "Anxiety",
            "sleep_quality": "SleepQuality",
        }[metric]
        scores[score_key] = max(0.0, min(100.0, value))

    citations: Dict[str, List[Citation]] = {}
    for rec_name in inp.receptors:
        canon = canonical_receptor_name(rec_name)
        if canon in refs:
            citations[canon] = refs[canon]

    details = {
        "raw_contributions": contrib,
        "final_scores": scores,
    }

    return SimulationOutput(scores=scores, details=details, citations=citations)
