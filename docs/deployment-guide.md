# Step-by-step hosting guide

This guide walks through three hosting options for the FastAPI backend so your Custom GPT can call it from anywhere on the internet. You can mix and match: host the API on Render or Hugging Face, then front it with the Cloudflare Worker to add caching, KV storage, and a simple diagnostics endpoint.

## Prerequisites

1. Fork or clone the repository.
2. Install Python 3.10 or newer plus Git on your local machine.
3. Copy the environment variables you plan to use (for example: `GRAPH_URI`, `GRAPH_USERNAME`, `GRAPH_PASSWORD`, `VECTOR_DB_URL`). Keep them handy—you will paste them into each platform’s settings.

---

## Option A: Render (fully managed backend)

Render runs the FastAPI app directly from this repository.

1. Sign in to [Render](https://render.com) and click **New → Web Service**.
2. Point the service at your fork on GitHub and tick **Use existing render.yaml** when prompted.
3. Keep the defaults from `render.yaml`:
   - **Runtime:** Python 3.10
   - **Build command:** `pip install -r backend/requirements.txt`
   - **Start command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables under the **Environment** tab. At minimum set `GRAPH_BACKEND`, `GRAPH_URI`, `GRAPH_USERNAME`, `GRAPH_PASSWORD`, and any vector database credentials.
5. Click **Create Web Service**. Render will install the dependencies and boot the app. Wait for the dashboard to show a healthy green status.
6. Visit the generated `https://<service-name>.onrender.com/assistant/capabilities` URL. You should see a JSON payload with the available actions—save this base URL for the Custom GPT and for the Cloudflare Worker setup below.

> **Need the mechanistic extras?** Switch the Render service to the Docker stack and install system libraries (`gfortran`, `cmake`, `libblas-dev`) before adding `pip install -e backend[mechanistic]`.

---

## Option B: Hugging Face Spaces (serverless FastAPI)

Hugging Face Spaces lets you run the backend on free hardware tiers.

1. Create a new **Space** and pick **FastAPI** as the template.
2. Upload these files into the Space:
   - `backend/` directory (you can copy the whole folder or zip and upload it).
   - A short entry script named `app.py` that imports the FastAPI app:
     ```python
     from backend.main import app
     ```
   - `requirements.txt` that simply references the backend requirements:
     ```text
     -r backend/requirements.txt
     ```
3. In the Space **Settings → Variables and secrets**, add the same environment variables used on Render (`GRAPH_*`, `VECTOR_DB_URL`, etc.).
4. Click **Restart**. The Space will rebuild, install the requirements, and expose a public URL such as `https://<space-owner>-<space-name>.hf.space`.
5. Open `https://<space-url>/assistant/capabilities` in a browser to confirm the API is live.

> **Tip:** For faster dependency installs, add a `pip-cache` secret (Personal Access Token) so the Space can pull cached wheels.

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
   npx wrangler kv:namespace create neuropharm-config
   npx wrangler d1 create neuropharm-vector-cache
   ```
   Copy the generated IDs into `wrangler.toml` under the `kv_namespaces` and `d1_databases` sections.
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

The backend validates the payload, executes the workflow, and returns structured JSON containing the normalised input plus the result data—no manual parsing required.

---

## Optional: orchestrate everything from the MCP CLI

If you prefer a command-line control plane, the repository now includes an MCP
bridge that forwards requests from [`mcp-cli`](https://github.com/chrishayuk/mcp-cli)
to your Render service, Cloudflare Worker, or Hugging Face Space. Follow the
step-by-step instructions in `docs/mcp-cli.md` to install the CLI, export your
deployment URLs, and launch an interactive session that can trigger any of the
assistant workflows without leaving the terminal.【F:docs/mcp-cli.md†L1-L92】
