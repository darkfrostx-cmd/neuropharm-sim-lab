# Neuropharm Simulation Lab

The Neuropharm Simulation Lab pairs a FastAPI knowledge-graph backend with a React
cockpit for exploring how neurotransmitter receptors combine to influence
behavioural outcomes. The stack ships with a pre-seeded evidence graph and a
mechanistic simulation engine so you can try ideas immediately—no external
services required.

## Quick tour for the impatient

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m backend.quickstart
```

The `backend.quickstart` helper runs a full simulation locally, prints a plain
English summary, and lists the knowledge graph sources that informed each
receptor weight. Use `python -m backend.quickstart --list-presets` to see the
built-in receptor mixes or add your own receptors on the fly, e.g.
`python -m backend.quickstart --receptor 5HT1A=0.7:agonist --receptor 5HT2A=0.2:antagonist`.

A step-by-step walkthrough with screenshots lives in
[`docs/getting-started-layman.md`](docs/getting-started-layman.md).

## Run the live API

1. **Create an environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```
2. **Start the server**
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
   The first boot automatically loads the seed graph stored in
   `backend/graph/data/seed_graph.json`. Visit `http://localhost:8000/docs` for
   an interactive OpenAPI explorer.
3. **Optional extras** – enable heavier simulation add-ons as needed:
   ```bash
   pip install -e backend[mechanistic]  # PySB, OSPSuite, TVB toolkits
   pip install -e backend[text-mining]  # Semantic Scholar + requests helpers
   pip install -e backend[causal]       # DoWhy/EconML counterfactuals
   ```

### Notable API capabilities

- **Assistant gateway** – `GET /assistant/capabilities` lists available actions
  and payload schemas for agent integrations. `POST /assistant/execute` runs an
  action for you, wrapping the underlying REST call and response.
- **Evidence explorer** – `POST /evidence/search` returns supporting studies for
  a subject/predicate/object triple. Evidence quality scores blend species,
  chronicity and design metadata so the most relevant items float to the top.
- **Simulation endpoint** – `POST /simulate` orchestrates molecular, PK/PD and
  circuit models. Responses include behavioural scores, confidence bands and
  receptor context.
- **Gap finder** – `POST /gaps` ranks missing edges between focus nodes and
  suggests literature leads to close them.

### Observability hooks

Set `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_ENABLED=1` for the Cloudflare Worker)
so the backend emits OpenTelemetry traces and metrics. Deployment metadata such
as `service.name` and `deployment.environment` are populated automatically.

## Start the dashboard

```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev -- --host 0.0.0.0 --port 5173
```

The Vite dev server proxies API calls to the backend URL in `.env.local`. When
you change a receptor in the UI the app calls `/predict/effects`, `/simulate`,
`/explain`, and `/gaps` behind the scenes while showing provenance badges, atlas
views (NiiVue) and Cytoscape graph neighbourhoods.

## Project map

```
neuropharm-sim-lab/
├── backend/
│   ├── api/                  # REST endpoints wired to graph + simulation services
│   ├── engine/               # Core receptor weights and helper utilities
│   ├── graph/                # Knowledge-graph store, evidence lookups and gap logic
│   ├── simulation/           # PK/PD + circuit orchestration scaffolding
│   ├── quickstart.py         # CLI helper for layman-friendly simulations
│   ├── requirements.txt      # Lean Python dependency set
│   ├── requirements-optional.txt
│   └── pyproject.toml        # Installable package with optional extras
├── frontend/                 # Vite/React cockpit (Cytoscape + NiiVue integrations)
├── docs/                     # Guides, deployment notes, and roadmap
├── infra/                    # Hugging Face Space, Render, and vector-store helpers
├── scripts/                  # Smoke tests and optional backend installers
├── Dockerfile                # Backend container image used for Render and local runs
└── render.yaml               # Render.com deployment recipe
```

## Quality checks

Run the guardrails before opening a pull request:

```bash
python -m compileall backend/main.py
pytest
cd frontend
npm test -- --watch=false
```

`pytest` exercises the API, graph bootstrapper, simulation pipeline and the new
quickstart CLI. `npm test` triggers the frontend unit tests; run it only if you
modified the UI.

## Need more detail?

- [`docs/deployment-guide.md`](docs/deployment-guide.md) – Render and Cloudflare
  Worker deployment playbooks.
- [`docs/mcp-cli.md`](docs/mcp-cli.md) – how to wire the API into MCP/agent
  clients.
- [`docs/blueprint-alignment.md`](docs/blueprint-alignment.md) – domain roadmap
  and research assumptions.

If anything is unclear, start with the layman guide linked above and then step
into the API docs once you feel comfortable.
