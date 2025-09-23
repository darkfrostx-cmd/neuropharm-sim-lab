# pgvector provisioning guide

The Neuropharm Simulation Lab keeps long-form embeddings (e.g. document
vectors) in a managed Postgres instance with the `pgvector` extension enabled.
Both [Supabase](https://supabase.com) and [Neon](https://neon.tech) expose a
free tier that works well for demos and day-to-day development. This folder
contains a small helper script to prime those databases.

## 1. Create the database

1. **Supabase** – Create a new project on the free tier. Once the database is
   provisioned, open *Project Settings → Database* and copy the *Connection
   string* (`postgresql://...`). Enable the `vector` extension from *Database →
   Extensions*.
2. **Neon** – Create a free project, then open *Project settings → Connection
   Details*. Copy the pooled connection string and enable the `vector`
   extension from the SQL console with `CREATE EXTENSION IF NOT EXISTS vector;`.

## 2. Prime the schema

Export the connection string as an environment variable and run the bootstrap
script:

```bash
export VECTOR_DB_URL="postgresql://user:pass@host:5432/postgres?sslmode=require"
./infra/pgvector/bootstrap_pgvector.sh
```

The script creates a dedicated schema (`neuropharm` by default), ensures the
`vector` extension is available and provisions a durable table for embedding
snapshots. Customise the following environment variables if you prefer
different names:

- `VECTOR_DB_SCHEMA` – Schema name (defaults to `neuropharm`).
- `VECTOR_DB_TABLE` – Table name (defaults to `embedding_cache`).
- `VECTOR_DB_DIMENSION` – Embedding dimensionality (defaults to 1536).

## 3. Wire the backend and Workers

Copy the emitted variables into your deployment environment:

- `VECTOR_DB_URL`
- `VECTOR_DB_SCHEMA`
- `VECTOR_DB_TABLE`

For GitHub-hosted CI/CD flows this means adding them to **Repository settings →
Secrets and variables → Actions**. For Cloudflare Workers, store them as
[encrypted secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
and set `VECTOR_DB_URL` (or the Supabase/Neon variants) at deploy time.

The FastAPI backend automatically reads these variables via
`backend.config.VectorStoreConfig` so ingestion jobs and future vector-based
features can open pooled connections without hardcoding credentials.
