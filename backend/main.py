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

from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any, Dict, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .engine.receptors import RECEPTORS, canonical_receptor_name
from .simulation import ReceptorInput, SimulationConfig, run_multiscale_pipeline


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
    ``exposure`` toggles between acute vs chronic assumptions across the
    PKPD and circuit layers, while ``propagate_uncertainty`` controls
    whether analytic uncertainty estimates are returned for each layer.
    """
    receptors: Dict[str, ReceptorSpec]
    acute_1a: bool = False
    adhd: bool = False
    gut_bias: bool = False
    pvt_weight: float = 0.5
    exposure: Literal["acute", "chronic"] = "acute"
    propagate_uncertainty: bool = True


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
    """Run the multiscale simulation pipeline with the provided input."""

    receptor_inputs: Dict[str, ReceptorInput] = {}
    for rec_name, spec in inp.receptors.items():
        canon = canonical_receptor_name(rec_name)
        if canon not in RECEPTORS:
            continue
        receptor_inputs[canon] = ReceptorInput(occupancy=spec.occ, mechanism=spec.mech)

    try:
        result = run_multiscale_pipeline(
            SimulationConfig(
                receptors=receptor_inputs,
                exposure=inp.exposure,
                adhd=inp.adhd,
                gut_bias=inp.gut_bias,
                pvt_weight=inp.pvt_weight,
                propagate_uncertainty=inp.propagate_uncertainty,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scores = dict(result.behavioural_scores)
    if inp.acute_1a:
        scores["Anxiety"] = max(0.0, scores.get("Anxiety", 50.0) - 5.0)
        scores["SleepQuality"] = min(100.0, scores.get("SleepQuality", 50.0) + 2.0)

    citations: Dict[str, list[Citation]] = {}
    for rec_name in receptor_inputs.keys():
        if rec_name in RECEPTOR_REFS:
            citations[rec_name] = [Citation(**ref) for ref in RECEPTOR_REFS[rec_name]]

    details = {
        "time": result.time,
        "molecular": asdict(result.molecular),
        "pkpd": asdict(result.pkpd),
        "circuit": asdict(result.circuit),
        "uncertainty": result.uncertainty_breakdown,
        "assumptions": {
            "exposure": inp.exposure,
            "propagate_uncertainty": inp.propagate_uncertainty,
            "acute_1a": inp.acute_1a,
        },
    }

    return SimulationOutput(scores=scores, details=details, citations=citations)
