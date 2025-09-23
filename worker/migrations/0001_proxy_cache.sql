-- Cache table for Cloudflare D1 backing the Worker edge proxy.
CREATE TABLE IF NOT EXISTS proxy_cache (
  cache_key TEXT PRIMARY KEY,
  status INTEGER NOT NULL,
  response TEXT NOT NULL,
  headers TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (cast(strftime('%s','now') as integer))
);
