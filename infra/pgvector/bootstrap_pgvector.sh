#!/usr/bin/env bash
#
# Configure a pgvector-ready Postgres database for the Neuropharm Simulation Lab.
#
# The script works with Supabase or Neon connection strings. Provide one of the
# following environment variables before running it:
#   - VECTOR_DB_URL (preferred)
#   - SUPABASE_DB_URL
#   - NEON_DB_URL
#   - DATABASE_URL (fallback)
#
# Example:
#   export VECTOR_DB_URL="postgresql://user:pass@host:5432/postgres?sslmode=require"
#   ./infra/pgvector/bootstrap_pgvector.sh
#
# Dependencies: `psql` must be available on PATH.

set -euo pipefail

CONNECTION_URL="${VECTOR_DB_URL:-${SUPABASE_DB_URL:-${NEON_DB_URL:-${DATABASE_URL:-}}}}"

if [[ -z "${CONNECTION_URL}" ]]; then
  echo "[!] Set VECTOR_DB_URL, SUPABASE_DB_URL, NEON_DB_URL or DATABASE_URL before running this script." >&2
  exit 1
fi

SCHEMA_NAME="${VECTOR_DB_SCHEMA:-neuropharm}"
TABLE_NAME="${VECTOR_DB_TABLE:-embedding_cache}"
EMBEDDING_DIMENSION="${VECTOR_DB_DIMENSION:-1536}"

PSQL_OPTS=("${CONNECTION_URL}" -v ON_ERROR_STOP=1)

echo "[*] Creating schema '${SCHEMA_NAME}' and table '${TABLE_NAME}' on ${CONNECTION_URL%%\?*}"

psql "${PSQL_OPTS[@]}" <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS ${SCHEMA_NAME};
CREATE TABLE IF NOT EXISTS ${SCHEMA_NAME}.${TABLE_NAME} (
  embedding_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  vector_value VECTOR(${EMBEDDING_DIMENSION}) NOT NULL,
  metadata JSONB DEFAULT '{}'::JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ${TABLE_NAME}_entity_type_idx ON ${SCHEMA_NAME}.${TABLE_NAME} (entity_type);
SQL

echo "[+] pgvector schema ready. Export the variables below so the backend can reach it:"
cat <<EOVARS
VECTOR_DB_URL=${CONNECTION_URL}
VECTOR_DB_SCHEMA=${SCHEMA_NAME}
VECTOR_DB_TABLE=${TABLE_NAME}
EOVARS
