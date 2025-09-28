"""STDIO MCP server that proxies Neuropharm deployments hosted on Render and Cloudflare."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_TIMEOUT_SECONDS = float(os.getenv("NEUROPHARM_MCP_TIMEOUT", "120"))
USER_AGENT = "neuropharm-mcp-bridge/0.1"

mcp = FastMCP(
    "Neuropharm Render Bridge",
    instructions=(
        "Proxy Neuropharm Simulation Lab deployments hosted on Render, Cloudflare, "
        "and Hugging Face. Configure NEUROPHARM_RENDER_URL, NEUROPHARM_WORKER_URL, "
        "or NEUROPHARM_HF_URL before launching the bridge."
    ),
)

_ENV_TARGETS: tuple[tuple[str, str], ...] = (
    ("render", "NEUROPHARM_RENDER_URL"),
    ("worker", "NEUROPHARM_WORKER_URL"),
    ("huggingface", "NEUROPHARM_HF_URL"),
    ("local", "NEUROPHARM_LOCAL_URL"),
)


def _available_targets() -> Dict[str, str]:
    """Return the configured target base URLs keyed by name."""

    mapping: Dict[str, str] = {}
    for key, env_name in _ENV_TARGETS:
        value = os.getenv(env_name)
        if value:
            mapping[key] = value.rstrip("/")
    if not mapping:
        mapping["local"] = os.getenv("NEUROPHARM_FALLBACK_URL", "http://127.0.0.1:8000").rstrip("/")
    return mapping


def _select_target(explicit: Optional[str] = None) -> tuple[str, str]:
    """Resolve the target identifier and base URL to use for a request."""

    targets = _available_targets()
    if explicit:
        key = explicit.lower()
        if key not in targets:
            raise ValueError(
                f"Unknown target '{explicit}'. Available targets: {', '.join(sorted(targets))}."
            )
        return key, targets[key]

    preferred = os.getenv("NEUROPHARM_DEFAULT_TARGET")
    if preferred and preferred.lower() in targets:
        key = preferred.lower()
        return key, targets[key]

    for key, _env_name in _ENV_TARGETS:
        if key in targets:
            return key, targets[key]

    key = next(iter(targets))
    return key, targets[key]


def _load_shared_headers() -> Dict[str, str]:
    """Build common HTTP headers, including optional API key injection."""

    headers: Dict[str, str] = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    shared_token = os.getenv("NEUROPHARM_API_KEY")
    if shared_token:
        headers.setdefault("Authorization", f"Bearer {shared_token}")

    extra_json = os.getenv("NEUROPHARM_EXTRA_HEADERS_JSON")
    if extra_json:
        try:
            extra = json.loads(extra_json)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive path
            raise ValueError(
                "NEUROPHARM_EXTRA_HEADERS_JSON must contain a JSON object"
            ) from exc
        if not isinstance(extra, Mapping):
            raise ValueError("NEUROPHARM_EXTRA_HEADERS_JSON must decode to an object")
        headers.update({str(k): str(v) for k, v in extra.items()})

    return headers


def _target_specific_headers(target: str) -> Dict[str, str]:
    """Apply target-specific overrides (API keys or additional headers)."""

    headers: Dict[str, str] = {}
    token_env = f"NEUROPHARM_{target.upper()}_API_KEY"
    token = os.getenv(token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    extra_env = f"NEUROPHARM_{target.upper()}_HEADERS_JSON"
    extra_json = os.getenv(extra_env)
    if extra_json:
        try:
            extra = json.loads(extra_json)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive path
            raise ValueError(f"{extra_env} must contain a JSON object") from exc
        if not isinstance(extra, Mapping):
            raise ValueError(f"{extra_env} must decode to an object")
        headers.update({str(k): str(v) for k, v in extra.items()})

    return headers


def _compose_headers(target: str) -> Dict[str, str]:
    headers = _load_shared_headers()
    headers.update(_target_specific_headers(target))
    return headers


def _make_url(base: str, path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return urljoin(base + "/", path.lstrip("/"))


def _serialize_response(response: httpx.Response, target: str, url: str) -> Dict[str, Any]:
    body: Dict[str, Any]
    try:
        body = {"json": response.json()}
    except ValueError:
        body = {"text": response.text}
    return {
        "target": target,
        "url": url,
        "status_code": response.status_code,
        "ok": response.is_success,
        "headers": {k: v for k, v in response.headers.items() if k.lower() in {"content-type", "cf-cache-status", "server"}},
        "body": body,
    }


async def _issue_request(
    method: str,
    path: str,
    *,
    target: Optional[str] = None,
    query: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    name, base = _select_target(target)
    url = _make_url(base, path)
    headers = _compose_headers(name)
    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method.upper(),
            url,
            params=query,
            json=payload,
            headers=headers,
        )
    payload_summary = _serialize_response(response, name, url)
    if not response.is_success:
        payload_summary["error"] = response.text
    return payload_summary


@mcp.tool(name="neuropharm.list_targets")
def list_targets() -> Dict[str, Any]:
    """List configured deployment targets and the active default selection."""

    targets = _available_targets()
    default_name, default_url = _select_target()
    return {
        "targets": targets,
        "default": {"name": default_name, "url": default_url},
        "environment": {
            env: os.getenv(env)
            for _key, env in _ENV_TARGETS
            if os.getenv(env)
        },
    }


@mcp.tool(name="neuropharm.fetch_capabilities")
async def fetch_capabilities(
    target: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Retrieve the ``/assistant/capabilities`` payload from a deployment."""

    return await _issue_request(
        "GET",
        "/assistant/capabilities",
        target=target,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool(name="neuropharm.execute_action")
async def execute_action(
    action: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    target: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Execute an assistant workflow by proxying ``/assistant/execute``."""

    request_payload = {"action": action, "payload": payload or {}}
    return await _issue_request(
        "POST",
        "/assistant/execute",
        target=target,
        payload=request_payload,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool(name="neuropharm.raw_request")
async def raw_request(
    method: str,
    path: str,
    *,
    target: Optional[str] = None,
    query: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Send an arbitrary HTTP request to the selected deployment."""

    return await _issue_request(
        method,
        path,
        target=target,
        query=query,
        payload=payload,
        timeout_seconds=timeout_seconds,
    )


if __name__ == "__main__":
    mcp.run()
