# Neuropharm Simulation Lab

The Neuropharm Simulation Lab couples a FastAPI knowledge graph backend with a
Vite/React analytics cockpit. The UI blends top-down atlas views (NiiVue), graph
neighbourhood navigation (Cytoscape) and bottom-up force projections to surface
receptor provenance, uncertainty and simulation outputs in one place.

## What lives where

```
neuropharm-sim-lab/
├── backend/
│   ├── api/                  # REST endpoints wired to graph + simulation services
│   ├── engine/               # Core receptor weight tables and helper utilities
│   ├── graph/                # Knowledge-graph store, evidence lookups and gaps logic
│   ├── simulation/           # PK/PD + circuit orchestration scaffolding
│   ├── requirements.txt      # Lean, Linux-friendly dependency set
│   └── requirements-optional.txt  # PySB/OSPSuite/TVB extras for research builds
├── frontend/
│   ├── src/                  # React components, hooks and styles
│   ├── tests/e2e/            # Playwright end-to-end coverage
│   └── playwright.config.ts  # Browser automation configuration
├── render.yaml               # Render.com deployment recipe for the backend API
└── README.md
```

## Quickstart

### 1. Backend API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The base requirements now ship with the Neo4j (5.x) and python-arango clients so
managed Aura and Oasis endpoints work without extra installs.

The optional simulation toolkits (PySB, OSPSuite, TVB) pull heavy native wheels.
Install them only when you need the full PK/PD stack:

```bash
pip install -r backend/requirements-optional.txt
```

**Render fix:** Render will happily install the lean requirements, but PySB’s
Fortran build chain fails on their default image. The included `render.yaml`
forces Python 3.10 and pins the build command to `pip install -r
backend/requirements.txt`, eliminating the broken optional wheel resolution. If
you do want the full simulation layer on Render, provision a starter instance
with the *Docker* stack and add system BLAS/LAPACK packages first.

### 2. Frontend cockpit

```bash
cd frontend
npm install
# Point the frontend at your API; defaults to same-origin
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev -- --host 0.0.0.0 --port 5173
```

Key features shipped by the React app:

- **Atlas overlays (NiiVue):** hash any selected receptor/node into deterministic
  MNI coordinates to keep the anatomical view responsive even without curated
  ROI volumes.
- **Graph neighbourhoods (Cytoscape + react-force-graph):** jump between
  top-down Cytoscape layouts and a bottom-up force graph with shared selection
  state.
- **Evidence workbench:** provenance cards, uncertainty badges and explanation
  trails for `/predict/effects` and `/explain` responses.
- **Simulation cockpit:** occupancy sliders, mechanism selectors, regimen
  toggles and a time cursor wired to `/simulate` outputs.

### 3. Tests and checks

Run the project guardrails after making changes:

```bash
python -m compileall backend/main.py
pytest
cd frontend
npm test -- --watch=false
```

`npm test` invokes both Vitest (unit) and Playwright (E2E) via a small wrapper
script so CI and local runs behave the same way.

## Deployment notes

### Graph connectivity environment variables

Configure the graph driver through environment variables before deploying to
Render, Cloudflare Workers or any other hosted stack:

```bash
GRAPH_BACKEND=neo4j
GRAPH_URI=neo4j+s://<neo4j-host>
GRAPH_USERNAME=<neo4j-user>
GRAPH_PASSWORD=<neo4j-password>

# Optional database selector when your Aura tenancy exposes multiple DBs
GRAPH_DATABASE=<neo4j-database>

# Mirror a managed ArangoDB instance (e.g. Oasis) alongside Aura
GRAPH_MIRROR_A_BACKEND=arangodb
GRAPH_MIRROR_A_URI=https://<arango-host>
GRAPH_MIRROR_A_DATABASE=<arango-database>
GRAPH_MIRROR_A_USERNAME=<arango-user>
GRAPH_MIRROR_A_PASSWORD=<arango-password>

# Enable strict TLS verification when the mirror requires SNI/cert checks
GRAPH_MIRROR_A_OPT_TLS=true
```

### GitHub Pages frontend

`.github/workflows/deploy-frontend.yml` now builds the React bundle before
publishing:

```yaml
- uses: actions/setup-node@v4
  with:
    node-version: '20'
    cache: npm
- run: cd frontend && npm ci && npm run build
- uses: peaceiris/actions-gh-pages@v3
  with:
    publish_dir: frontend/dist
```

Enable Pages → GitHub Actions in your repository settings and pushes to `main`
will redeploy automatically.

### Render.com backend

The new `render.yaml` captures the working configuration. Deploy by connecting
the repo and selecting “Use existing `render.yaml`”. Render will:

- Pin the runtime to Python 3.10 where the lean requirements have prebuilt
  wheels.
- Install only `backend/requirements.txt` to avoid the PySB/ospsuite build
  failures shown in the earlier screenshots.
- Launch Uvicorn with `backend.main:app` on the assigned `$PORT`.
- Ship the Neo4j (`neo4j>=5.13.0`) and ArangoDB (`python-arango>=7.5.5`) drivers by
  default so managed Aura and Oasis clusters work without extra installs. Aura
  refuses older 4.x drivers, so keep the requirement on the 5.x line or newer.

If you later need the optional toolkits, switch the service to the Docker stack
or run the install step inside a job that preinstalls `gfortran`, `cmake` and
`libblas-dev`.

### Zero-cost edge + database stack

You can run the full stack on free tiers by pairing the API with Cloudflare and
serverless databases:

1. **Frontend.** Deploy the React bundle to [Cloudflare Pages][cf-pages] (free,
   unlimited requests). Pages can also host the static NiiVue shader assets.
2. **API.** Use [Cloudflare Workers][cf-workers] to proxy requests to a Render
   instance or to a lightweight container running the FastAPI app. The backend
   reads its connection info from environment variables, so Workers KV can store
   secrets safely.
3. **Graph storage.** Point the backend at a free [Neo4j Aura][aura] instance by
   setting `GRAPH_BACKEND=neo4j` and `GRAPH_URI=neo4j+s://...`. Install the
   backend requirements so the Neo4j and ArangoDB clients are available, then
   mirror writes to ArangoDB (or any document store) with the new mirror syntax:

   ```bash
   pip install -r backend/requirements.txt
   GRAPH_BACKEND=neo4j
   GRAPH_URI=neo4j+s://<your-host>
   GRAPH_USERNAME=<user>
   GRAPH_PASSWORD=<password>
   GRAPH_MIRROR_A_BACKEND=arangodb
   GRAPH_MIRROR_A_URI=https://<your-arango-host>
   GRAPH_MIRROR_A_DATABASE=brainos
   ```

   The bundled `python-arango>=7.5.5` release contains the TLS/SNI fixes that
   ArangoDB Oasis and other managed offerings require. If you override the
   version pin, keep it at 7.5 or newer so certificate negotiation succeeds.

   `GraphConfig` automatically creates a composite store that keeps the Aura
   graph and the Arango document view in sync.
4. **Vectors and documents.** [Supabase][supabase] or [Neon][neon] provide free
   Postgres/pgvector tiers; the ingestion jobs can push embeddings there while
   the main graph stays in Aura.

The `render.yaml` remains for teams already invested in Render, but the Cloudflare
setup gives you an entirely free footprint for demos and day-to-day research.

### Automated ingestion runs

`backend/graph/cli.py` exposes the ingestion pipeline as a CLI:

```bash
python -m backend.graph.cli ingest --job ChEMBL --limit 100
```

Jobs honour cooldown windows via the new `IngestionOrchestrator`, and state is
persisted to `backend/graph/data/ingestion_state.json`. A scheduled GitHub
Action (`.github/workflows/ingestion.yml`) executes `python -m
backend.graph.cli ingest --limit 50` every morning (UTC) so Aura/Arango mirrors
stay fresh without manual intervention. Before enabling the workflow, create the
following GitHub secrets so the runner can reach your managed graph instances:

| Secret(s) | Required | Purpose |
| --- | --- | --- |
| `GRAPH_BACKEND`, `GRAPH_URI`, `GRAPH_USERNAME`, `GRAPH_PASSWORD` | ✔️ | Connection settings for the primary Neo4j Aura deployment (e.g. `neo4j+s://<hostname>`). |
| `GRAPH_DATABASE` | Optional | Only necessary when your Aura project expects an explicit database name. |
| `GRAPH_MIRROR_A_BACKEND`, `GRAPH_MIRROR_A_URI`, `GRAPH_MIRROR_A_DATABASE` | ✔️ (if mirroring) | Location of the ArangoDB (or other supported) mirror that receives replicated writes. |
| `GRAPH_MIRROR_A_USERNAME`, `GRAPH_MIRROR_A_PASSWORD` | ✔️ (if mirroring) | Service credentials for the mirror user. |
| `GRAPH_MIRROR_A_OPT_TLS` | Optional | Set to `true` to enforce TLS verification when the mirror requires it. |

Add additional `GRAPH_MIRROR_<NAME>_*` secrets if you replicate to more than one
store; the ingestion CLI automatically discovers them during each run.

[cf-pages]: https://developers.cloudflare.com/pages/
[cf-workers]: https://developers.cloudflare.com/workers/
[aura]: https://neo4j.com/cloud/aura/
[supabase]: https://supabase.com
[neon]: https://neon.tech

## Frontend data hooks

All React components talk to the backend through composable hooks in
`src/hooks/apiHooks.js`:

- `useGraphExpand` → `/graph/expand`
- `usePredictEffects` → `/predict/effects`
- `useExplain` → `/explain`
- `useGapFinder` → `/gaps`
- `useSimulation` → `/simulate`

Each hook exposes `{ status, data, error, execute, reset }` so you can chain
workflows (e.g. populate the simulation cockpit once the evidence cards arrive).
Utility helpers also emit Cytoscape element lists and force-graph payloads from
the shared response model.

## Contributing

Follow the guardrails documented in `AGENTS.md`:

1. Keep commits focused and accompany code changes with relevant docs/tests.
2. Run the compile step, `pytest`, and `npm test -- --watch=false` before
   opening a PR.
3. Document any optional dependency requirements when you extend the simulator
   or graph ingestion stack.

Questions or feedback? File an issue or start a discussion—new receptors,
visual encodings, or ingestion jobs are always welcome.

