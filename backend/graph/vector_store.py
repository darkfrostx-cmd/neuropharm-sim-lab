"""Vector-store abstractions for gap ranking."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    import psycopg
    from psycopg import sql
except Exception:  # pragma: no cover - optional dependency
    psycopg = None  # type: ignore[assignment]
    sql = None  # type: ignore[assignment]

from ..config import VectorStoreConfig


@dataclass(slots=True)
class VectorRecord:
    """Representation of a stored embedding."""

    id: str
    vector: Tuple[float, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float | None = None


class BaseVectorStore:
    """Abstract persistence layer used by the gap finder."""

    def upsert(self, namespace: str, records: Iterable[VectorRecord]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def delete_namespace(self, namespace: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def query(
        self,
        namespace: str,
        vector: Sequence[float],
        *,
        top_k: int = 10,
    ) -> List[VectorRecord]:  # pragma: no cover - interface
        raise NotImplementedError

    def get(self, namespace: str, record_id: str) -> VectorRecord | None:  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryVectorStore(BaseVectorStore):
    """Simple cosine-similarity implementation for tests and local runs."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, VectorRecord]] = {}

    def upsert(self, namespace: str, records: Iterable[VectorRecord]) -> None:
        bucket = self._store.setdefault(namespace, {})
        for record in records:
            bucket[record.id] = record

    def delete_namespace(self, namespace: str) -> None:
        self._store.pop(namespace, None)

    def query(self, namespace: str, vector: Sequence[float], *, top_k: int = 10) -> List[VectorRecord]:
        bucket = self._store.get(namespace)
        if not bucket:
            return []
        query_vec = tuple(float(x) for x in vector)
        scored: List[Tuple[float, VectorRecord]] = []
        for record in bucket.values():
            similarity = self._cosine_similarity(query_vec, record.vector)
            record.score = similarity
            scored.append((similarity, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:top_k]]

    def get(self, namespace: str, record_id: str) -> VectorRecord | None:
        bucket = self._store.get(namespace)
        if not bucket:
            return None
        return bucket.get(record_id)

    @staticmethod
    def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        if len(vec_a) != len(vec_b) or not vec_a:
            return -1.0
        dot = sum(float(a) * float(b) for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(float(a) ** 2 for a in vec_a))
        norm_b = math.sqrt(sum(float(b) ** 2 for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return -1.0
        return float(dot / (norm_a * norm_b))


class SqliteVectorStore(BaseVectorStore):
    """File-backed store that keeps embeddings across process restarts."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    namespace TEXT NOT NULL,
                    id TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    metadata TEXT,
                    score REAL,
                    updated_at REAL DEFAULT (strftime('%s','now')),
                    PRIMARY KEY(namespace, id)
                )
                """
            )

    def upsert(self, namespace: str, records: Iterable[VectorRecord]) -> None:
        payload = [
            (
                namespace,
                record.id,
                json.dumps(list(record.vector)),
                json.dumps(record.metadata or {}),
                record.score,
            )
            for record in records
        ]
        if not payload:
            return
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO vectors(namespace, id, vector, metadata, score)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(namespace, id) DO UPDATE SET
                    vector = excluded.vector,
                    metadata = excluded.metadata,
                    score = excluded.score,
                    updated_at = strftime('%s','now')
                """,
                payload,
            )

    def delete_namespace(self, namespace: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM vectors WHERE namespace = ?", (namespace,))

    def query(self, namespace: str, vector: Sequence[float], *, top_k: int = 10) -> List[VectorRecord]:
        query_vec = tuple(float(x) for x in vector)
        with self._conn:
            rows = self._conn.execute(
                "SELECT id, vector, metadata, score FROM vectors WHERE namespace = ?",
                (namespace,),
            ).fetchall()
        scored: List[Tuple[float, VectorRecord]] = []
        for record_id, vector_json, metadata_json, score_val in rows:
            try:
                stored_vector = tuple(float(x) for x in json.loads(vector_json))
            except Exception:
                continue
            similarity = InMemoryVectorStore._cosine_similarity(query_vec, stored_vector)
            metadata = json.loads(metadata_json) if metadata_json else {}
            scored.append(
                (
                    similarity,
                    VectorRecord(
                        id=str(record_id),
                        vector=stored_vector,
                        metadata=dict(metadata),
                        score=similarity,
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:top_k]]

    def get(self, namespace: str, record_id: str) -> VectorRecord | None:
        with self._conn:
            row = self._conn.execute(
                "SELECT vector, metadata, score FROM vectors WHERE namespace = ? AND id = ?",
                (namespace, record_id),
            ).fetchone()
        if not row:
            return None
        vector_json, metadata_json, score_val = row
        try:
            vector = tuple(float(x) for x in json.loads(vector_json))
        except Exception:
            return None
        metadata = json.loads(metadata_json) if metadata_json else {}
        return VectorRecord(id=record_id, vector=vector, metadata=dict(metadata), score=score_val)


class PgVectorStore(BaseVectorStore):  # pragma: no cover - optional dependency
    """pgvector-backed store used in production deployments."""

    def __init__(self, config: VectorStoreConfig) -> None:
        if psycopg is None or sql is None:
            raise ImportError("psycopg is required for PgVectorStore")
        self.config = config
        self._schema = config.schema or "public"
        self._table = config.table or "embedding_cache"
        self._conn = self._connect()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _connect(self) -> "psycopg.Connection[tuple[()]]":
        if self.config.dsn:
            return psycopg.connect(self.config.dsn)  # type: ignore[arg-type]
        return psycopg.connect(  # type: ignore[arg-type]
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.database,
            user=self.config.username,
            password=self.config.password,
        )

    def _ensure_schema(self, dimension: int) -> None:
        with self._conn.cursor() as cur:  # type: ignore[arg-type]
            schema_stmt = sql.SQL("CREATE SCHEMA IF NOT EXISTS {}" ).format(sql.Identifier(self._schema))
            cur.execute(schema_stmt)
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception:
                self._conn.rollback()
            else:
                self._conn.commit()
        with self._conn.cursor() as cur:  # type: ignore[arg-type]
            create_table = sql.SQL(
                "CREATE TABLE IF NOT EXISTS {}.{} ("
                " namespace TEXT NOT NULL,"
                " id TEXT NOT NULL,"
                " embedding vector({}),"
                " metadata JSONB,"
                " score DOUBLE PRECISION,"
                " updated_at TIMESTAMPTZ DEFAULT NOW(),"
                " PRIMARY KEY(namespace, id)"
                ")"
            ).format(
                sql.Identifier(self._schema),
                sql.Identifier(self._table),
                sql.SQL(str(int(dimension))),
            )
            cur.execute(create_table)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Interface implementation
    # ------------------------------------------------------------------
    def upsert(self, namespace: str, records: Iterable[VectorRecord]) -> None:
        records = list(records)
        if not records:
            return
        dimension = len(records[0].vector)
        self._ensure_schema(dimension)
        with self._conn.cursor() as cur:  # type: ignore[arg-type]
            statement = sql.SQL(
                "INSERT INTO {}.{} (namespace, id, embedding, metadata, score)"
                " VALUES (%s, %s, %s, %s::jsonb, %s)"
                " ON CONFLICT (namespace, id)"
                " DO UPDATE SET embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata,"
                " score = EXCLUDED.score, updated_at = NOW()"
            ).format(sql.Identifier(self._schema), sql.Identifier(self._table))
            payload = [
                (
                    namespace,
                    record.id,
                    list(record.vector),
                    json.dumps(record.metadata or {}),
                    record.score,
                )
                for record in records
            ]
            cur.executemany(statement, payload)
            self._conn.commit()

    def delete_namespace(self, namespace: str) -> None:
        with self._conn.cursor() as cur:  # type: ignore[arg-type]
            statement = sql.SQL("DELETE FROM {}.{} WHERE namespace = %s").format(
                sql.Identifier(self._schema), sql.Identifier(self._table)
            )
            cur.execute(statement, (namespace,))
            self._conn.commit()

    def query(self, namespace: str, vector: Sequence[float], *, top_k: int = 10) -> List[VectorRecord]:
        query_vec = tuple(float(x) for x in vector)
        with self._conn.cursor() as cur:  # type: ignore[arg-type]
            statement = sql.SQL(
                "SELECT id, embedding, metadata, score FROM {}.{}"
                " WHERE namespace = %s"
                " ORDER BY embedding <-> %s"
                " LIMIT %s"
            ).format(sql.Identifier(self._schema), sql.Identifier(self._table))
            cur.execute(statement, (namespace, list(query_vec), top_k))
            rows = cur.fetchall()
        results: List[VectorRecord] = []
        for row in rows:
            record_id: str = row[0]
            embedding_raw: Sequence[float] = row[1]
            metadata_raw = row[2] or {}
            score_val = row[3]
            metadata = metadata_raw if isinstance(metadata_raw, dict) else json.loads(metadata_raw)
            embedding = tuple(float(x) for x in embedding_raw)
            similarity = InMemoryVectorStore._cosine_similarity(query_vec, embedding)
            results.append(
                VectorRecord(
                    id=record_id,
                    vector=embedding,
                    metadata=dict(metadata),
                    score=similarity if similarity >= 0 else score_val,
                )
            )
        return results

    def get(self, namespace: str, record_id: str) -> VectorRecord | None:
        with self._conn.cursor() as cur:  # type: ignore[arg-type]
            statement = sql.SQL(
                "SELECT embedding, metadata, score FROM {}.{} WHERE namespace = %s AND id = %s"
            ).format(sql.Identifier(self._schema), sql.Identifier(self._table))
            cur.execute(statement, (namespace, record_id))
            row = cur.fetchone()
        if not row:
            return None
        embedding, metadata_raw, score_val = row
        metadata = metadata_raw if isinstance(metadata_raw, dict) else json.loads(metadata_raw or "{}")
        return VectorRecord(
            id=record_id,
            vector=tuple(float(x) for x in embedding),
            metadata=dict(metadata),
            score=score_val,
        )



def build_vector_store(config: VectorStoreConfig | None) -> BaseVectorStore:
    if config and config.is_configured():
        try:
            return PgVectorStore(config)
        except Exception:
            return InMemoryVectorStore()
    if config and config.sqlite_path:
        try:
            return SqliteVectorStore(config.sqlite_path)
        except Exception:
            return InMemoryVectorStore()
    return InMemoryVectorStore()


__all__ = [
    "BaseVectorStore",
    "InMemoryVectorStore",
    "SqliteVectorStore",
    "PgVectorStore",
    "VectorRecord",
    "build_vector_store",
]

