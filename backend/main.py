"""FastAPI application entry-point for the Neuropharm simulation API."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import create_router
from .graph.service import GraphService
from .simulation import SimulationEngine


app = FastAPI(
    title="Neuropharm Simulation API",
    description=(
        "Simulate serotonergic, dopaminergic and other neurotransmitter systems "
        "under diverse receptor manipulations, inspect graph evidence, and "
        "generate mechanism-aware explanations."
    ),
)

origins = os.environ.get("CORS_ORIGINS", "https://darkfrostx-cmd.github.io").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_graph_service = GraphService()
_simulation_engine = SimulationEngine(time_step=1.0)

app.state.graph_service = _graph_service
app.state.simulation_engine = _simulation_engine

app.include_router(create_router(graph_service=_graph_service, simulation_engine=_simulation_engine))


@app.get("/")
def read_root() -> dict[str, str]:
    """Health check endpoint."""

    return {"status": "ok", "version": "2025.09.05"}


@app.get("/health")
def health() -> dict[str, str]:
    """Alias for :func:`read_root` used by uptime monitors."""

    return {"status": "ok", "version": "2025.09.05"}
