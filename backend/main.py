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
    get_receptor_weights,
)
from .simulation import EngineRequest, ReceptorEngagement, SimulationEngine


Mechanism = Literal["agonist", "antagonist", "partial", "inverse"]


REFS_PATH = Path(__file__).with_name("refs.json")
try:
    with REFS_PATH.open("r", encoding="utf-8") as f:
        RECEPTOR_REFS: dict[str, list[dict[str, str]]] = json.load(f)
except FileNotFoundError:
    RECEPTOR_REFS = {}

ENGINE = SimulationEngine(time_step=1.0)

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
    dosing: Literal["acute", "chronic"] = "chronic"
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
    mechanisms involved in generating the result.  `confidence` provides a
    0–1 certainty estimate for each behavioural score.
    """
    scores: Dict[str, float]
    details: Dict[str, Any]
    citations: Dict[str, list[Citation]]
    confidence: Dict[str, float]


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
    """Run a single simulation with the provided input."""

    regimen: Literal["acute", "chronic"] = inp.dosing
    if inp.acute_1a:
        regimen = "acute"

    engagements: Dict[str, ReceptorEngagement] = {}
    for rec_name, spec in inp.receptors.items():
        canon = canonical_receptor_name(rec_name)
        if canon not in RECEPTORS:
            continue
        weights = get_receptor_weights(canon)
        if weights:
            kg_weight = sum(abs(w) for w in weights.values()) / len(weights)
        else:
            kg_weight = 0.25
        evidence = min(0.95, 0.45 + 0.1 * len(RECEPTOR_REFS.get(canon, [])))
        engagements[canon] = ReceptorEngagement(
            name=canon,
            occupancy=spec.occ,
            mechanism=spec.mech,
            kg_weight=kg_weight,
            evidence=evidence,
        )

    engine_request = EngineRequest(
        receptors=engagements,
        regimen=regimen,
        adhd=inp.adhd,
        gut_bias=inp.gut_bias,
        pvt_weight=inp.pvt_weight,
    )

    try:
        result = ENGINE.run(engine_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    citations: Dict[str, list[Citation]] = {}
    for rec_name in inp.receptors.keys():
        canon = canonical_receptor_name(rec_name)
        if canon in RECEPTOR_REFS:
            citations[canon] = [Citation(**ref) for ref in RECEPTOR_REFS[canon]]

    details = {
        "timepoints": result.timepoints,
        "trajectories": result.trajectories,
        "modules": result.module_summaries,
    }

    return SimulationOutput(
        scores=result.scores,
        details=details,
        citations=citations,
        confidence=result.confidence,
    )
