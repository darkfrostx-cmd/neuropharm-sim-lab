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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Dict, Literal

import json
import os
from pathlib import Path

from .engine.receptors import (
    RECEPTORS,
    canonical_receptor_name,
    get_mechanism_factor,
    get_receptor_weights,
)


Mechanism = Literal["agonist", "antagonist", "partial", "inverse"]


REFS_PATH = Path(__file__).with_name("refs.json")
try:
    with REFS_PATH.open("r", encoding="utf-8") as f:
        RECEPTOR_REFS: dict[str, list[dict[str, str]]] = json.load(f)
except FileNotFoundError:
    RECEPTOR_REFS = {}

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
    occ: float = Field(ge=0.0, le=1.0)
    mech: Mechanism


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
    """Return format from the simulation engine.

    `scores` contains high‑level behavioural metrics normalised to 0–100.
    `details` includes intermediate values (e.g. computed dopamine phasic
    drive) that may be useful for debugging or future UI visualisations.
    `citations` returns a list of PubMed IDs and/or DOIs supporting the
    mechanisms involved in generating the result.
    """
    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, list[Citation]]


# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------

app = FastAPI(title="Neuropharm Simulation API",
              description=("Simulate serotonergic, dopaminergic and other\n                           neurotransmitter systems under a variety of\n                           receptor manipulations.  See the README for\n                           details on the expected payload format."))

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

    # Initialise metric contributions.  Baseline of 50 for each metric.
    metrics = [
        "drive",
        "apathy",
        "motivation",
        "cognitive_flexibility",
        "anxiety",
        "sleep_quality",
    ]
    contrib: Dict[str, float] = {m: 0.0 for m in metrics}

    # Accumulate contributions from each receptor in the input.  For
    # unknown receptors, silently ignore.  Mechanism factor scales the
    # per‑unit weight; occupancy scales the contribution.
    for rec_name, spec in inp.receptors.items():
        canon = canonical_receptor_name(rec_name)
        if canon not in RECEPTORS:
            continue
        weights = get_receptor_weights(canon)
        try:
            factor = get_mechanism_factor(spec.mech)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for m, w in weights.items():
            contrib[m] += w * spec.occ * factor

    # Apply phenotype modifiers.  ADHD reduces baseline tone for drive
    # and motivation; gut_bias attenuates negative contributions (makes
    # apathy less severe and drive more preserved); acute_1a lowers
    # overall serotonergic effect (scale contributions down).
    if inp.adhd:
        contrib["drive"] -= 0.3
        contrib["motivation"] -= 0.2
    if inp.gut_bias:
        for m in metrics:
            # If contribution is negative, reduce its magnitude by 10%
            if contrib[m] < 0:
                contrib[m] *= 0.9
    if inp.acute_1a:
        for m in metrics:
            contrib[m] *= 0.75
    # PVT gating weight scales contributions from 5-HT1B (if present);
    # approximate by scaling global contributions by (1 - pvt_weight*0.2)
    contrib_scale = 1.0 - (inp.pvt_weight * 0.2)
    for m in metrics:
        contrib[m] *= contrib_scale

    # Convert contributions to scores.  Baseline is 50; each unit of
    # contribution moves the score by 20 points.  Clamp between 0 and
    # 100.  Note: for apathy, higher contribution increases apathy; for
    # other metrics, contributions add directly.
    scores: Dict[str, float] = {}
    for m in metrics:
        base = 50.0
        change = 20.0 * contrib[m]
        val = base + change
        # Invert apathy into ApathyBlunting (higher apathy = lower score)
        if m == "apathy":
            val = 100.0 - val
        scores_name = {
            "drive": "DriveInvigoration",
            "apathy": "ApathyBlunting",
            "motivation": "Motivation",
            "cognitive_flexibility": "CognitiveFlexibility",
            "anxiety": "Anxiety",
            "sleep_quality": "SleepQuality",
        }[m]
        scores[scores_name] = max(0.0, min(100.0, val))

    # Build citations dictionary: gather references for each receptor used.
    citations: Dict[str, list[Citation]] = {}
    for rec_name in inp.receptors.keys():
        canon = canonical_receptor_name(rec_name)
        if canon in RECEPTOR_REFS:
            citations[canon] = [Citation(**ref) for ref in RECEPTOR_REFS[canon]]

    details = {
        "raw_contributions": contrib,
        "final_scores": scores,
    }

    return SimulationOutput(scores=scores, details=details, citations=citations)
