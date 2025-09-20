"""FastAPI application entrypoint for the Neuropharm Simulation Lab."""

from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import api_router

DESCRIPTION = (
    "Explore neuromodulator dynamics and curated literature support via a "
    "unified API. Simulation endpoints expose the Neuropharm receptor "
    "occupancy model, while graph utilities surface evidence from the "
    "knowledge graph assembled from INDRA, OpenAlex, ChEMBL, and atlas "
    "resources."
)

app = FastAPI(
    title="Neuropharm Simulation API",
    description=DESCRIPTION,
    version="0.2.0",
    contact={
        "name": "Neuropharm Simulation Lab",
        "url": "https://github.com/darkfrostx-cmd/neuropharm-sim-lab",
        "email": "neuropharm-sim-lab@example.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {"name": "Simulation", "description": "Run receptor-based simulations and effect predictions."},
        {"name": "Evidence", "description": "Search and explain curated literature evidence."},
        {"name": "Graph", "description": "Explore the knowledge graph topology and gaps."},
    ],
)

origins = os.environ.get("CORS_ORIGINS", "https://darkfrostx-cmd.github.io").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root() -> dict[str, str]:
    """Root health-check endpoint."""

    return {"status": "ok", "version": app.version}


@app.get("/health")
def health() -> dict[str, str]:
    """Secondary health endpoint for monitoring systems."""

    return {"status": "ok", "version": app.version}


app.include_router(api_router)
