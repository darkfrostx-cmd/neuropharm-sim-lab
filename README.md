# Neuropharm Simulation Lab

The Neuropharm Simulation Lab couples a FastAPI knowledge graph backend with a
Vite/React analytics cockpit. The UI blends top-down atlas views (NiiVue), graph
neighbourhood navigation (Cytoscape) and bottom-up force projections to surface
receptor provenance, uncertainty and simulation outputs in one place.

The evidence backbone ingests ChEMBL, BindingDB, IUPHAR and the PDSP Ki dataset
out of the box, keeping ligand–receptor affinities and provenance cards close to
the simulation layer.

## What lives where

```
neuropharm-sim-lab/
├── backend/
│   ├── api/                  # REST endpoints wired to graph + simulation services
│   ├── engine/               # Core receptor weight tables and helper utilities
│   ├── graph/                # Knowledge-graph store, evidence lookups and gaps logic
│   ├── simulation/           # PK/PD + circuit orchestration scaffolding
│   ├── requirements.txt      # Lean, Linux-friendly dependency set
│   ├── requirements-optional.txt  # Legacy pin set for manual installs
│   └── pyproject.toml        # Installable package with optional simulation extras
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

#### Programmatic assistant gateway

Custom GPTs and other agent-style clients can call the API through a single
entrypoint without hand-coding each workflow. Two new endpoints surface the
available actions and execute them on behalf of the caller:

```text
GET  /assistant/capabilities   # Lists supported actions + JSON Schemas
POST /assistant/execute        # Dispatches an action with a validated payload
```

For example, predicting receptor evidence reduces to:

```bash
curl -X POST http://localhost:8000/assistant/execute \
  -H "Content-Type: application/json" \
  -d '{
        "action": "predict_effects",
        "payload": {"receptors": [{"name": "5HT1A"}]}
      }'
```

The response bundles the underlying REST endpoint, a normalised payload and the
result body so agent frameworks can reason over inputs and outputs with minimal
custom code. This gateway works transparently behind the provided Cloudflare
Worker proxy and can be deployed to a FastAPI-ready Hugging Face Space by
pointing `app = backend.main.app` inside your Space entry script.

The optional simulation toolkits (PySB, OSPSuite, TVB) pull heavy native wheels.
Install them only when you need the full PK/PD stack:

```bash
pip install -e backend[mechanistic]
```

This extra now bundles ready-to-run assets in `backend/simulation/assets`:

- `pysb_reference_pathway.json` (PySB): seeded with the HTR2A → ERK cascade so
  full ODE integration kicks in automatically when PySB is present.
- `pbpk_reference_project.json` (OSPSuite): a PBPK model that mirrors the analytic
  fallback used by the default engine; install OSPSuite to run the full
  compartmental simulation.
- `tvb_reference_connectivity.json` (TVB): a lightweight structural connectome
  used by the circuit module when the Virtual Brain stack is available.

Users on the “free” stack can enable each backend independently:

```bash
pip install -e backend[text-mining]  # adds requests + optional scispaCy extras
pip install -e backend[mechanistic]  # PySB + OSPSuite + TVB
pip install -e backend[causal]       # DoWhy/EconML counterfactual diagnostics
```

Each extra extends the API responses transparently—counterfactual requests begin
returning refutation diagnostics once the causal extra is installed, and the
simulation endpoints automatically switch from the analytic fallback to the
mechanistic engines when the corresponding toolkits are present.

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

- **Atlas overlays (NiiVue):** the crosshair now anchors to true anatomical
  centroids from the Allen Brain Atlas, and the viewer streams the official
  10 µm CCF annotation volume plus EBRAINS surface meshes when available.
  Hash-based fallbacks remain in place when no provenance is known.
- **Graph neighbourhoods (Cytoscape + react-force-graph):** jump between
  top-down Cytoscape layouts and a bottom-up force graph with shared selection
  state.
- **Evidence workbench:** provenance cards, uncertainty badges and explanation
  trails for `/predict/effects` and `/explain` responses.
- **Simulation cockpit:** occupancy sliders, mechanism selectors, regimen
  toggles, chronic plasticity controls (TrkB facilitation, α2A HCN closure)
  and a time cursor wired to `/simulate` outputs. Behavioural scores are now
  annotated with RDoC and Cognitive Atlas identifiers so downstream analyses
  can reuse standard vocabularies.

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

## Automated literature text mining

OpenAlex ingestion now pipes works through a GROBID → scispaCy → INDRA-inspired
pipeline.  The default configuration is intentionally light-weight—the
`TextMiningPipeline` falls back to deterministic pattern matching when spaCy
models are unavailable—yet the structure mirrors a production deployment:

1. PDFs are converted to TEI with the GROBID HTTP API (set `GROBID_URL` to point
   at your instance).
2. TEI text is parsed with scispaCy when the `en_core_sci_sm` model is installed,
   otherwise a rule-based extractor looks for *activates/inhibits/modulates*
   phrases.
3. Candidate relations are assembled into Biolink nodes/edges and persisted with
   provenance so downstream services can surface the textual snippet.

You can enable the richer NLP stack by installing scispaCy and the associated
models:

```bash
pip install scispacy
python -m spacy download en_core_sci_sm
```

Point the ingestion orchestrator at a running GROBID container by exporting
`GROBID_URL=http://localhost:8070` before executing the OpenAlex job.

## Deployment notes

### Graph connectivity environment variables

Configure the graph driver through environment variables before deploying to
Render, Cloudflare Workers or any other hosted stack. If you want a spoon-fed walkthrough for Render, Hugging Face Spaces, and the Cloudflare Worker, follow [`docs/deployment-guide.md`](docs/deployment-guide.md).

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

1. **Graph storage (Neo4j + optional mirrors).** Point the backend at a free
   [Neo4j Aura][aura] instance by setting `GRAPH_BACKEND=neo4j` and
   `GRAPH_URI=neo4j+s://...`. Install the backend requirements so the Neo4j and
   ArangoDB clients are available, then mirror writes to ArangoDB (or any
   document store) with the existing mirror syntax:

   ```bash
   pip install -r backend/requirements.txt
   export GRAPH_BACKEND=neo4j
   export GRAPH_URI=neo4j+s://<your-host>
   export GRAPH_USERNAME=<user>
   export GRAPH_PASSWORD=<password>
   export GRAPH_MIRROR_A_BACKEND=arangodb
   export GRAPH_MIRROR_A_URI=https://<your-arango-host>
   export GRAPH_MIRROR_A_DATABASE=brainos
   ```

   The bundled `python-arango>=7.5.5` release contains the TLS/SNI fixes that
   ArangoDB Oasis and other managed offerings require. If you override the
   version pin, keep it at 7.5 or newer so certificate negotiation succeeds.
   `GraphConfig` automatically creates a composite store that keeps the Aura
   graph and the Arango document view in sync.
2. **Vector embeddings (Supabase/Neon).** Free [Supabase][supabase] and
   [Neon][neon] projects expose pgvector-enabled Postgres instances. The helper
   script in `infra/pgvector/bootstrap_pgvector.sh` provisions the extension and
   baseline tables:

   ```bash
   export VECTOR_DB_URL="postgresql://user:pass@host:5432/postgres?sslmode=require"
   ./infra/pgvector/bootstrap_pgvector.sh
   ```

   Copy the emitted variables (`VECTOR_DB_URL`, `VECTOR_DB_SCHEMA`,
   `VECTOR_DB_TABLE`) into your deployment environment. The backend loads them
   via `backend.config.VectorStoreConfig` and keeps them available for ingestion
   jobs and Worker sidecars.
3. **API via Cloudflare Workers.** The `wrangler.toml` at the repository root
   points Wrangler at `worker/src/index.ts`, a lightweight proxy that forwards
   requests to FastAPI, stores secrets in Workers KV and caches hot responses in
   D1. To deploy manually:

   ```bash
   cd worker
   npm install
   npx wrangler kv:namespace create neuropharm-config
   npx wrangler d1 create neuropharm-vector-cache
   npx wrangler secret put API_BASE_URL   # e.g. https://your-render-service.onrender.com
   npx wrangler secret put VECTOR_DB_URL  # optional, falls back to KV for reads
   npx wrangler deploy --var API_BASE_URL:https://your-backend.example
   ```

   Store long-lived secrets (graph credentials, Postgres URLs) in the KV
   namespace so the Worker can hydrate `API_BASE_URL` when the direct variable
   is missing. The Worker exposes `GET /__worker/health` for quick diagnostics
   and automatically persists cacheable JSON responses to the D1 database.
4. **Frontend via Cloudflare Pages.** Build the React bundle and ship it to
   Pages:

   ```bash
   cd frontend
   npm ci
   npm run build
   npx wrangler pages deploy dist --project-name neuropharm-sim-lab
   ```

   Set `VITE_API_BASE_URL` to the public Worker URL so the frontend targets the
   proxy instead of a direct Render instance.

GitHub deployments are wired through `.github/workflows/deploy-cloudflare.yml`.
Add the following repository secrets before enabling the workflow:

| Secret | Purpose |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account identifier for Pages/Workers. |
| `CLOUDFLARE_API_TOKEN` | Scoped token with `Pages` and `Workers KV/D1` permissions. |
| `CLOUDFLARE_PAGES_PROJECT` | Name of the Pages project receiving the frontend build. |
| `WORKER_API_BASE_URL` | Backend URL injected at deploy time (`wrangler deploy --var`). |
| `VECTOR_DB_URL` | Connection string passed through to the Worker and backend. |

The workflow builds the frontend, publishes it to Pages, installs the Worker
dependencies and runs `wrangler deploy`. The `render.yaml` remains for teams
already invested in Render, but the Cloudflare setup gives you an entirely free
footprint for demos and day-to-day research.

### Automated ingestion runs

`backend/graph/cli.py` exposes the ingestion pipeline as a CLI:

```bash
python -m backend.graph.cli ingest --job ChEMBL --limit 100
```

Jobs honour cooldown windows via the new `IngestionOrchestrator`, and state is
persisted to `backend/graph/data/ingestion_state.json`. A scheduled GitHub
Action (`.github/workflows/ingestion.yml`) executes `python -m
backend.graph.cli ingest --limit 50` every morning (UTC) so Aura/Arango mirrors
stay fresh without manual intervention. Populate the following GitHub **Secrets**
(Settings → *Secrets and variables* → *Actions*) so the workflow can
authenticate against your managed graph instances:

| Secret | Required? | Purpose |
| --- | --- | --- |
| `GRAPH_BACKEND` | Yes | Backend driver for the primary store (e.g. `neo4j`). |
| `GRAPH_URI` | Yes | Connection string for Aura (`neo4j+s://<hostname>`) or another Neo4j cluster. |
| `GRAPH_USERNAME` | Yes | Aura/Neo4j username with write access. |
| `GRAPH_PASSWORD` | Yes | Matching password or generated token. |
| `GRAPH_DATABASE` | Optional | Explicit database name when the cluster exposes multiple DBs. |
| `GRAPH_OPT_TLS` | Optional | Set to `true` to force TLS verification when Aura requires strict cert checks. |
| `GRAPH_MIRROR_A_BACKEND` | Optional | Backend identifier for the first mirror (e.g. `arangodb`). |
| `GRAPH_MIRROR_A_URI` | Optional | Mirror connection URL such as `https://<arango-host>`. |
| `GRAPH_MIRROR_A_DATABASE` | Optional | Target database within the mirror instance. |
| `GRAPH_MIRROR_A_USERNAME` | Optional | Mirror user allowed to upsert nodes/edges. |
| `GRAPH_MIRROR_A_PASSWORD` | Optional | Password for the mirror user. |
| `GRAPH_MIRROR_A_OPT_TLS` | Optional | Set to `true` when the mirror enforces TLS/SNI validation. |

Add additional `GRAPH_MIRROR_<NAME>_*` secrets if you replicate to more than
one store; the ingestion CLI automatically discovers them during each run.

After provisioning the secrets, trigger a staging dry-run from **Actions →
Refresh knowledge graph → Run workflow**. The job output prints a summary for
each ingestion plan (records processed, nodes created, edges created) so you can
confirm that data lands in the persistent store before re-enabling the daily
schedule. For local smoke tests you can export the same variables and run
`python -m backend.graph.cli ingest --limit 25` to exercise the pipeline without
waiting for GitHub Actions.

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

