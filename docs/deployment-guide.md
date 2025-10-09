# Step-by-step hosting guide

This guide walks through three hosting options for the FastAPI backend so your Custom GPT can call it from anywhere on the internet. You can mix and match: host the API on Render or Hugging Face, then front it with the Cloudflare Worker to add caching, KV storage, and a simple diagnostics endpoint.

## Prerequisites

1. Fork or clone the repository.
2. Install Python 3.10 or newer plus Git on your local machine.
3. Copy the environment variables you plan to use (for example: `GRAPH_URI`, `GRAPH_USERNAME`, `GRAPH_PASSWORD`, `VECTOR_DB_URL`). Keep them handy—you will paste them into each platform’s settings.
4. Install optional bundles as needed. The text-mining upgrade (spaCy 3.7/scispaCy 0.5.4) ships behind the extras interface, so run `pip install -e backend[text-mining]` on hosts that execute ingestion or evidence scoring workflows.【F:backend/pyproject.toml†L30-L45】

### Install the mechanistic solver bundle locally

Run the helper script from the repository root to install PySB, The Virtual Brain, and (optionally) OSPSuite into your virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
INSTALL_OSPSUITE=0 scripts/install_mechanistic_backends.sh
```

> **Need OSPSuite?** Request access to the [OSPSuite Azure Artifacts feed](https://www.open-systems-pharmacology.org/). Then rerun the script with either `OSPSUITE_INDEX_URL=https://pkgs.dev.azure.com/<org>/<project>/_packaging/OSPSuite/pypi/simple/` or `OSPSUITE_WHEEL_URL=https://.../ospsuite-<version>-py3-none-manylinux2014_x86_64.whl`. The script automatically installs the pinned PySB and TVB versions and will add the OSPSuite wheel when credentials are supplied.

---

## Option A: Render (fully managed backend)

Render runs the FastAPI app directly from this repository.

1. Sign in to [Render](https://render.com) and click **New → Web Service**.
2. Point the service at your fork on GitHub and tick **Use existing render.yaml** when prompted.
3. Keep the defaults from `render.yaml`:
   - **Runtime:** Python 3.10
   - **Build command:** `pip install -r backend/requirements.txt`
   - **Start command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables under the **Environment** tab. At minimum set `GRAPH_BACKEND`, `GRAPH_URI`, `GRAPH_USERNAME`, `GRAPH_PASSWORD`, and any vector database credentials. To enable the heavy solvers in production, add `MOLECULAR_SIM_BACKEND=high_fidelity`, `PKPD_SIM_BACKEND=high_fidelity`, and `CIRCUIT_SIM_BACKEND=high_fidelity` once OSPSuite/TVB are installed.
5. Click **Create Web Service**. Render will install the dependencies and boot the app. Wait for the dashboard to show a healthy green status.
6. Visit the generated `https://<service-name>.onrender.com/assistant/capabilities` URL. You should see a JSON payload with the available actions—save this base URL for the Custom GPT and for the Cloudflare Worker setup below.

> **Need the mechanistic extras?** Switch the Render service to the Docker stack and reuse the repository’s `Dockerfile`. Provide any private OSPSuite feed credentials as build arguments:
> ```bash
> render.yaml:
>   services:
>     - type: web
>       name: neuropharm-backend
>       env: docker
>       plan: starter
>       dockerCommand: >-
>         --build-arg OSPSUITE_INDEX_URL=${OSPSUITE_INDEX_URL}
>         --build-arg OSPSUITE_VERSION=${OSPSUITE_VERSION}
> ```
> When the `/simulate` endpoint runs with the mechanistic stack enabled it reports which backend executed in the `engine.backends` object so you can confirm the upgrade immediately.

---

## Option B: Hugging Face Spaces (serverless FastAPI)

Hugging Face Spaces lets you run the backend on free hardware tiers.

1. Create a new **Space** and pick **FastAPI** as the template.
2. Upload these files into the Space:
   - `backend/` directory (you can copy the whole folder or zip and upload it).
   - The helper files from `hf_space/` (`app.py` and `requirements.txt`) which already contain the correct import and dependency
     references.
3. In the Space **Settings → Variables and secrets**, add the same environment variables used on Render (`GRAPH_*`, `VECTOR_DB_URL`, etc.).
4. Click **Restart**. The Space will rebuild, install the requirements, and expose a public URL such as `https://<space-owner>-<space-name>.hf.space`.
5. Open `https://<space-url>/assistant/capabilities` in a browser to confirm the API is live.

> **Tip:** For faster dependency installs, add a `pip-cache` secret (Personal Access Token) so the Space can pull cached wheels.

> **Mechanistic add-on:** Add an additional **Build step** in the Space UI: `bash scripts/install_mechanistic_backends.sh`. Set `INSTALL_OSPSUITE=0` if you just want the open-source PySB/TVB bundle, or point `OSPSUITE_WHEEL_URL` at the official wheel to include OSPSuite.

---

## Option C: Cloudflare Worker (edge proxy + “memory”)

Deploy the Worker once you have a reachable backend (Render, Hugging Face, or any HTTPS host). The Worker adds KV storage for long-term config and a D1 database to cache responses.

1. Install the toolchain locally:
   ```bash
   cd worker
   npm install
   ```
2. Create the storage bindings:
   ```bash
   npx wrangler kv namespace create neuropharm-config
   npx wrangler d1 create neuropharm-vector-cache
   ```
   Copy the generated IDs into `wrangler.toml` under the `kv_namespaces` and `d1_databases` sections. The Worker expects the KV
   binding to be named `NEUROPHARM_CONFIG` and the D1 binding to be `VECTOR_CACHE`, both already declared in the template
   `wrangler.toml` file.
3. Seed secrets and default variables:
   ```bash
   npx wrangler secret put API_BASE_URL      # e.g. https://your-render-service.onrender.com
   npx wrangler secret put VECTOR_DB_URL     # optional, can also live in KV
   npx wrangler kv:key put neuropharm-config api_base_url https://your-backend-url
   ```
4. Apply the bundled D1 migration so the cache table exists:
   ```bash
   npx wrangler d1 migrations apply neuropharm-vector-cache
   ```
5. Deploy the Worker:
  ```bash
  npx wrangler deploy --var API_BASE_URL:https://your-backend-url
  ```
6. Verify the health endpoint at `https://<worker-subdomain>/__worker/health`. All bindings should report `ok`. If anything says `missing`, re-check the namespace IDs and secrets.
7. Point your Custom GPT at the Worker instead of the origin backend. Use the Worker URL for both `/assistant/capabilities` and `/assistant/execute`. The Worker forwards requests, adds caching headers, and keeps “memory” in KV and D1.

---

## Next steps: connect to a Custom GPT

Once any of the hosts above is running, register two actions in the Custom GPT builder:

1. **Capabilities lookup** – `GET https://<your-host>/assistant/capabilities`
2. **Action executor** – `POST https://<your-host>/assistant/execute`

For each execution action, send a JSON body shaped like:
```json
{
  "action": "predict_effects",
  "payload": {
    "receptors": [{ "name": "5HT1A" }]
  }
}
```

> **Runtime visibility:** The `/simulate` response now includes an `engine` object detailing which solver executed (`engine.backends`) and any fallbacks triggered (`engine.fallbacks`). Surface these fields in cockpit telemetry to verify when the high-fidelity stack is engaged.

The backend validates the payload, executes the workflow, and returns structured JSON containing the normalised input plus the result data—no manual parsing required.

---

## Optional: orchestrate everything from the MCP CLI

If you prefer a command-line control plane, the repository now includes an MCP
bridge that forwards requests from [`mcp-cli`](https://github.com/chrishayuk/mcp-cli)
to your Render service, Cloudflare Worker, or Hugging Face Space. Follow the
step-by-step instructions in `docs/mcp-cli.md` to install the CLI, export your
deployment URLs, and launch an interactive session that can trigger any of the
assistant workflows without leaving the terminal.【F:docs/mcp-cli.md†L1-L92】
