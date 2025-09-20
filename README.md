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

If you later need the optional toolkits, switch the service to the Docker stack
or run the install step inside a job that preinstalls `gfortran`, `cmake` and
`libblas-dev`.

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

