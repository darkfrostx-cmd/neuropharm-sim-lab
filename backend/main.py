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
from typing import Any, Dict, Iterable, List

import json
import os

from fastapi import FastAPI
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
    contrib: Dict[str, float] = {metric: 0.0 for metric in METRICS}

    # Accumulate contributions from each receptor in the input.  For
    # unknown receptors, silently ignore.  Mechanism factor scales the
    # per‑unit weight; occupancy scales the contribution.
    for rec_name, spec in inp.receptors.items():
        canon = canonical_receptor_name(rec_name)
        if canon not in RECEPTORS:
            continue
        weights = get_receptor_weights(canon)
        factor = get_mechanism_factor(spec.mech)
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
        for m in METRICS:
            # If contribution is negative, reduce its magnitude by 10%
            if contrib[m] < 0:
                contrib[m] *= 0.9
    if inp.acute_1a:
        for m in METRICS:
            contrib[m] *= 0.75
    # PVT gating weight scales contributions from 5-HT1B (if present);
    # approximate by scaling global contributions by (1 - pvt_weight*0.2)
    contrib_scale = 1.0 - (inp.pvt_weight * 0.2)
    for m in METRICS:
        contrib[m] *= contrib_scale

    # Convert contributions to scores.  Baseline is 50; each unit of
    # contribution moves the score by 20 points.  Clamp between 0 and
    # 100.  Note: for apathy, higher contribution increases apathy; for
    # other metrics, contributions add directly.
    scores: Dict[str, float] = {}
    for metric in METRICS:
        base = 50.0
        change = 20.0 * contrib[metric]
        value = base + change
        if metric == "apathy":
            value = 100.0 - value
        scores_name = SCORE_KEY_MAP[metric]
        scores[scores_name] = max(0.0, min(100.0, value))

    # Build citations dictionary: gather references for each receptor used.
    citations: Dict[str, List[Citation]] = {}
    for rec_name in inp.receptors.keys():
        canon = canonical_receptor_name(rec_name)
        refs = REFERENCES.get(canon)
        if refs:
            citations[canon] = [Citation(**ref) for ref in refs]

    details = {
        "raw_contributions": contrib,
        "final_scores": scores,
    }

    return SimulationOutput(scores=scores, details=details, citations=citations)
