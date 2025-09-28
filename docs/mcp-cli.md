# Using the MCP CLI with Neuropharm Simulation Lab

This guide shows how to drive the Neuropharm Simulation Lab deployments (Render,
Cloudflare Worker, and Hugging Face Space) from the open-source
[`mcp-cli`](https://github.com/chrishayuk/mcp-cli) tooling. The repository ships a
ready-to-run MCP bridge that proxies HTTP requests to the deployed FastAPI
backend so that `mcp-cli` can call the same workflows your Render service
exposes.

## 1. Install the MCP tooling

Create a clean virtual environment and install the helper dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r infra/mcp/requirements.txt
```

The requirements file pins compatible versions of `mcp`, `mcp-cli`, and the
HTTP client used by the bridge server.【F:infra/mcp/requirements.txt†L1-L4】

## 2. Configure deployment endpoints

Export the URLs for every deployment you want to route through the bridge.
You can set as many as you need—Render, the Cloudflare Worker fronting KV/D1,
and a Hugging Face Space are all supported out of the box.【F:infra/mcp/render_bridge.py†L24-L59】

```bash
export NEUROPHARM_RENDER_URL="https://<your-render-service>.onrender.com"
export NEUROPHARM_WORKER_URL="https://<your-worker-subdomain>.workers.dev"
export NEUROPHARM_HF_URL="https://<your-space>.hf.space"
export NEUROPHARM_DEFAULT_TARGET=worker   # optional, defaults to the first configured URL
```

If a deployment requires authentication, provide an API key using one of the
optional environment variables listed below:

| Purpose | Environment variable | Notes |
| --- | --- | --- |
| Shared Authorization header | `NEUROPHARM_API_KEY` | Applied to every target unless overridden. |
| Render-specific token | `NEUROPHARM_RENDER_API_KEY` | Overrides the shared key when calling Render. |
| Cloudflare Worker token | `NEUROPHARM_WORKER_API_KEY` | Useful when the Worker enforces bearer auth. |
| Extra headers (JSON) | `NEUROPHARM_EXTRA_HEADERS_JSON` | JSON object of additional headers (e.g. `{"CF-Worker": "edge"}`). |

All variables are consumed by the bridge before each request so you can adjust
them without restarting `mcp-cli`.【F:infra/mcp/render_bridge.py†L61-L119】

## 3. Point `mcp-cli` at the bridge

Copy the provided configuration template to a location that `mcp-cli` can read
(such as `~/.config/mcp-cli/server_config.json`) and replace the placeholder URLs
with your deployment endpoints.【F:infra/mcp/server_config.json†L1-L15】

```bash
mkdir -p ~/.config/mcp-cli
cp infra/mcp/server_config.json ~/.config/mcp-cli/server_config.json
$EDITOR ~/.config/mcp-cli/server_config.json
```

The template already wires the `neuropharm-render` server entry to run the bridge
via `python -m infra.mcp.render_bridge`. If you prefer to keep the configuration
inside the repository, pass `--config-file infra/mcp/server_config.json` to every
`mcp-cli` command instead of copying the file.

## 4. Launch the bridge and start chatting

With the environment variables set, start an interactive MCP session that uses
the Worker URL by default:

```bash
mcp-cli chat --server neuropharm-render \
  --config-file infra/mcp/server_config.json \
  --provider openai --model gpt-4o-mini
```

During the session you can:

- Run `/tools` to list the available helpers (`neuropharm.list_targets`,
  `neuropharm.fetch_capabilities`, `neuropharm.execute_action`, and
  `neuropharm.raw_request`).【F:infra/mcp/render_bridge.py†L121-L173】
- Execute a workflow from the Render backend:
  `/cmd neuropharm.execute_action action=simulate payload='{"dose_mg": 20}'`
- Switch targets at runtime by passing `target="render"` (Render service) or
  `target="huggingface"` when calling a tool.【F:infra/mcp/render_bridge.py†L78-L173】

Every tool response includes the upstream URL, HTTP status, a parsed JSON body
(if available), and the headers that are useful for debugging cache hits coming
from Cloudflare.【F:infra/mcp/render_bridge.py†L101-L112】

## 5. Troubleshooting tips

| Symptom | Fix |
| --- | --- |
| `Unknown target 'worker'` errors | Ensure `NEUROPHARM_WORKER_URL` is exported before launching the bridge.【F:infra/mcp/render_bridge.py†L31-L47】 |
| Authentication failures | Double-check the relevant `NEUROPHARM_*_API_KEY` value or inspect the returned headers for clues.【F:infra/mcp/render_bridge.py†L80-L114】 |
| Timeouts on heavy workflows | Increase `NEUROPHARM_MCP_TIMEOUT` or pass `timeout_seconds` when invoking a tool.【F:infra/mcp/render_bridge.py†L16-L17】【F:infra/mcp/render_bridge.py†L94-L136】 |

Once the CLI is connected you can take advantage of Render’s mechanistic build,
Cloudflare’s KV/D1 caching layer, and the Hugging Face Space simultaneously from
a single MCP session.
