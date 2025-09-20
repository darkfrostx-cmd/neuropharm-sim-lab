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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any

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


class SimulationOutput(BaseModel):
    """Return format from the simulation engine.

    `scores` contains high-level behavioural metrics normalised to 0–100.
    `details` includes intermediate values (e.g. computed dopamine phasic
    drive) that may be useful for debugging or future UI visualisations.
    `citations` returns a list of PubMed IDs and/or DOIs supporting the
    mechanisms involved in generating the result.
    """

    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, list[Dict[str, str]]]


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

# Configure CORS based on environment variable to allow the GitHub Pages front-end.
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
    """Secondary health check endpoint used by some monitoring scripts."""

    return {"status": "ok", "version": "2025.09.05"}


@app.post("/simulate", response_model=SimulationOutput)
def simulate(inp: SimulationInput) -> SimulationOutput:
    """Run a single simulation with the provided input.

    This function currently implements a highly simplified scoring
    algorithm. It computes phasic dopamine drive based on 5-HT2C and
    5-HT1B occupancy, modulates it with ADHD state and gut-bias flags,
    and then maps the result into overall "Drive" and "Apathy" scores.

    Parameters
    ----------
    inp : SimulationInput
        The payload specifying receptor occupancies and modifiers.

    Returns
    -------
    SimulationOutput
        A dictionary containing high-level scores, intermediate details
        and citations underpinning the mechanisms used.
    """

    # ---------------------------------------------------------------------
    # Helper functions
    # ---------------------------------------------------------------------
    def canonical_receptor_name(name: str) -> str:
        """Normalise receptor identifiers to the canonical key.

        Accepts legacy names such as "5HT2C" and returns the hyphenated
        form ("5-HT2C") used in the RECEPTORS mapping.
        """

        if name in RECEPTORS:
            return name
        # Normalise names like "5HT2C" → "5-HT2C" and "5ht1a" → "5-HT1A"
        name_upper = name.upper().replace("HT", "-HT")
        return name_upper

    # Load receptor citations from refs.json.  This file should map
    # canonical receptor names to lists of PubMed IDs or DOIs.
    try:
        refs_path = os.path.join(os.path.dirname(__file__), "refs.json")
        with open(refs_path, "r", encoding="utf-8") as f:
            refs = json.load(f)
    except FileNotFoundError:
        refs = {}

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

    # Accumulate contributions from each receptor in the input.
    for rec_name, spec in inp.receptors.items():
        canon = canonical_receptor_name(rec_name)
        if canon not in RECEPTORS:
            continue
        weights = get_receptor_weights(canon)
        factor = get_mechanism_factor(spec.mech)
        for m, w in weights.items():
            contrib[m] += w * spec.occ * factor

    # Apply phenotype modifiers.
    if inp.adhd:
        contrib["drive"] -= 0.3
        contrib["motivation"] -= 0.2
    if inp.gut_bias:
        for m in metrics:
            if contrib[m] < 0:
                contrib[m] *= 0.9
    if inp.acute_1a:
        for m in metrics:
            contrib[m] *= 0.75

    # PVT gating weight scales contributions from 5-HT1B (if present).
    contrib_scale = 1.0 - (inp.pvt_weight * 0.2)
    for m in metrics:
        contrib[m] *= contrib_scale

    # Convert contributions to scores with a baseline of 50.
    scores: Dict[str, float] = {}
    for m in metrics:
        base = 50.0
        change = 20.0 * contrib[m]
        val = base + change
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
    citations: Dict[str, list[Dict[str, str]]] = {}
    for rec_name in inp.receptors.keys():
        canon = canonical_receptor_name(rec_name)
        if canon in refs:
            citations[canon] = refs[canon]

    details = {
        "raw_contributions": contrib,
        "final_scores": scores,
    }

    return SimulationOutput(scores=scores, details=details, citations=citations)
