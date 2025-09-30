export interface Env {
  API_BASE_URL?: string;
  CACHE_TTL_SECONDS?: string;
  NEUROPHARM_CONFIG?: KVNamespace;
  VECTOR_CACHE?: D1Database;
}

const CACHEABLE_METHODS = new Set(["GET"]);
const CACHEABLE_STATUS = new Set([200, 203]);
const MAX_CACHE_BODY_BYTES = 120_000;

async function resolveBackendBase(env: Env): Promise<string | null> {
  const direct = env.API_BASE_URL?.trim();
  if (direct) {
    return direct;
  }
  try {
    const kvValue = await env.NEUROPHARM_CONFIG?.get("api_base_url");
    if (kvValue && kvValue.trim()) {
      return kvValue.trim();
    }
  } catch (error) {
    console.warn("KV lookup for api_base_url failed", error);
  }
  return null;
}

function joinPaths(basePath: string, requestPath: string): string {
  if (!basePath || basePath === "/") {
    return requestPath;
  }
  const trimmedBase = basePath.endsWith("/") ? basePath.slice(0, -1) : basePath;
  const trimmedRequest = requestPath.startsWith("/") ? requestPath.slice(1) : requestPath;
  return `${trimmedBase}/${trimmedRequest}`;
}

function sanitiseHeaders(headers: Headers): Headers {
  const result = new Headers();
  headers.forEach((value, key) => {
    if (key.toLowerCase() === "host") {
      return;
    }
    result.set(key, value);
  });
  return result;
}

function cacheKeyFromUrl(url: URL): string {
  return `${url.pathname}?${url.searchParams.toString()}`;
}

async function readFromCache(env: Env, cacheKey: string, ttlSeconds: number): Promise<Response | null> {
  const db = env.VECTOR_CACHE;
  if (!db) {
    return null;
  }
  try {
    const row = await db
      .prepare(
        `SELECT response, status, headers, updated_at FROM proxy_cache WHERE cache_key = ?1`,
      )
      .bind(cacheKey)
      .first<Record<string, unknown>>();
    if (!row) {
      return null;
    }
    const updatedAt = Number(row["updated_at"] ?? 0);
    const nowSeconds = Math.floor(Date.now() / 1000);
    if (!Number.isFinite(updatedAt) || nowSeconds - updatedAt > ttlSeconds) {
      return null;
    }
    const responseText = String(row["response"] ?? "");
    const status = Number(row["status"] ?? 200);
    const rawHeaders = row["headers"] ? JSON.parse(String(row["headers"])) : [];
    const headers = new Headers();
    if (Array.isArray(rawHeaders)) {
      for (const [key, value] of rawHeaders) {
        headers.set(String(key), String(value));
      }
    }
    headers.set("CF-Worker-Cache", "HIT");
    return new Response(responseText, { status, headers });
  } catch (error) {
    console.warn("Failed to read from D1 cache", error);
    return null;
  }
}

async function persistToCache(
  env: Env,
  cacheKey: string,
  response: Response,
): Promise<void> {
  const db = env.VECTOR_CACHE;
  if (!db) {
    return;
  }
  try {
    const clone = response.clone();
    const buffer = await clone.arrayBuffer();
    if (buffer.byteLength > MAX_CACHE_BODY_BYTES) {
      return;
    }
    const text = new TextDecoder().decode(buffer);
    const headersJson = JSON.stringify(Array.from(response.headers.entries()));
    await db
      .prepare(
        `INSERT INTO proxy_cache (cache_key, status, response, headers, updated_at)
         VALUES (?1, ?2, ?3, ?4, cast(strftime('%s','now') as integer))
         ON CONFLICT(cache_key) DO UPDATE SET
           status = excluded.status,
           response = excluded.response,
           headers = excluded.headers,
           updated_at = excluded.updated_at`,
      )
      .bind(cacheKey, response.status, text, headersJson)
      .run();
  } catch (error) {
    console.warn("Failed to persist response to D1 cache", error);
  }
}

function shouldCacheResponse(response: Response): boolean {
  if (!CACHEABLE_STATUS.has(response.status)) {
    return false;
  }
  const cacheControl = response.headers.get("Cache-Control") ?? "";
  if (/no-store|private/i.test(cacheControl)) {
    return false;
  }
  const contentType = response.headers.get("Content-Type") ?? "";
  return contentType.includes("application/json");
}

function parseTtl(env: Env): number {
  const raw = env.CACHE_TTL_SECONDS ? Number(env.CACHE_TTL_SECONDS) : NaN;
  if (Number.isFinite(raw) && raw > 0) {
    return raw;
  }
  return 60;
}

function buildHealthPayload(env: Env, backendBase: string | null): Response {
  const payload = {
    status: "ok",
    backend: backendBase,
    cache: env.VECTOR_CACHE ? "enabled" : "disabled",
    configNamespace: env.NEUROPHARM_CONFIG ? "bound" : "unbound",
  };
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/__worker/health") {
      const backendBase = await resolveBackendBase(env);
      return buildHealthPayload(env, backendBase);
    }

    const backendBase = await resolveBackendBase(env);
    if (!backendBase) {
      return new Response(
        JSON.stringify({ error: "API backend not configured", code: "backend_missing" }),
        {
          status: 500,
          headers: { "content-type": "application/json; charset=utf-8" },
        },
      );
    }

    const ttlSeconds = parseTtl(env);
    const cacheKey = cacheKeyFromUrl(url);

    if (CACHEABLE_METHODS.has(request.method.toUpperCase())) {
      const cached = await readFromCache(env, cacheKey, ttlSeconds);
      if (cached) {
        return cached;
      }
    }

    const upstream = new URL(backendBase);
    upstream.pathname = joinPaths(upstream.pathname, url.pathname);
    upstream.search = url.search;
    upstream.hash = url.hash;

    const headers = sanitiseHeaders(new Headers(request.headers));
    const init: RequestInit = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (request.method.toUpperCase() !== "GET" && request.method.toUpperCase() !== "HEAD") {
      init.body = await request.arrayBuffer();
    }

    const backendResponse = await fetch(upstream.toString(), init);
    const responseHeaders = new Headers(backendResponse.headers);
    responseHeaders.set("CF-Worker-Cache", "MISS");

    const response = new Response(backendResponse.body, {
      status: backendResponse.status,
      statusText: backendResponse.statusText,
      headers: responseHeaders,
    });

    if (
      CACHEABLE_METHODS.has(request.method.toUpperCase()) &&
      shouldCacheResponse(response) &&
      env.VECTOR_CACHE
    ) {
      ctx.waitUntil(persistToCache(env, cacheKey, response));
    }

    return response;
  },
};
