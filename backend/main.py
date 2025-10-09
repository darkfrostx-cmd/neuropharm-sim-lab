"""FastAPI application entrypoint for the Neuropharm Simulation Lab."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import configure_services, router as api_router
from .config import DEFAULT_TELEMETRY_CONFIG
from .graph.ingest_runner import bootstrap_graph
from .graph.service import GraphService
from .simulation import GraphBackedReceptorAdapter, SimulationEngine
from .telemetry import configure_telemetry


API_DESCRIPTION = """
The Neuropharm Simulation API couples a mechanistic SSRI simulation engine
with a knowledge graph describing receptor level evidence.  The service
exposes endpoints to:

* query evidence supporting edges in the knowledge graph (`/evidence/search`)
* expand the graph around a node (`/graph/expand`)
* derive receptor effects used by the simulator (`/predict/effects`)
* run a multi-layer pharmacology simulation (`/simulate`)
* explain receptor inputs by surfacing supporting evidence (`/explain`)
* highlight gaps between focus nodes (`/gaps`)

Use the OpenAPI schema for complete request/response examples.
"""


REFS_PATH = Path(__file__).with_name("refs.json")
try:
    with REFS_PATH.open("r", encoding="utf-8") as handle:
        RECEPTOR_REFS: dict[str, list[dict[str, str]]] = json.load(handle)
except FileNotFoundError:
    RECEPTOR_REFS = {}


telemetry = configure_telemetry(DEFAULT_TELEMETRY_CONFIG)


app = FastAPI(title="Neuropharm Simulation API", description=API_DESCRIPTION)
telemetry.instrument_app(app)


origins = os.environ.get("CORS_ORIGINS", "https://darkfrostx-cmd.github.io").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


AUTO_BOOTSTRAP = os.environ.get("GRAPH_AUTO_BOOTSTRAP", "1").lower() not in {"0", "false", "no"}

graph_service = GraphService()
if AUTO_BOOTSTRAP:
    bootstrap_graph(graph_service)
simulation_engine = SimulationEngine(time_step=1.0)
receptor_adapter = GraphBackedReceptorAdapter(graph_service)

configure_services(
    graph_service=graph_service,
    simulation_engine=simulation_engine,
    receptor_adapter=receptor_adapter,
    receptor_references=RECEPTOR_REFS,
)


app.include_router(api_router)


@app.get("/")
def read_root() -> dict[str, str]:
    """Basic health check used by the frontend shell."""

    return {"status": "ok", "version": "2025.09.05"}


@app.get("/health")
def health() -> dict[str, str]:
    """Alias of :func:`read_root` for compatibility with uptime monitors."""

    return {"status": "ok", "version": "2025.09.05"}


__all__ = ["app"]
