from backend.config import VectorStoreConfig
from pathlib import Path

from backend.graph.vector_store import (
    InMemoryVectorStore,
    SqliteVectorStore,
    VectorRecord,
    build_vector_store,
)


def test_inmemory_vector_store_queries_by_cosine_similarity() -> None:
    store = InMemoryVectorStore()
    store.upsert(
        "nodes",
        [
            VectorRecord(id="A", vector=(1.0, 0.0), metadata={"node_id": "A"}),
            VectorRecord(id="B", vector=(0.0, 1.0), metadata={"node_id": "B"}),
        ],
    )
    results = store.query("nodes", (0.9, 0.1), top_k=1)
    assert results
    assert results[0].id == "A"


def test_build_vector_store_falls_back_when_not_configured() -> None:
    config = VectorStoreConfig()
    store = build_vector_store(config)
    assert isinstance(store, SqliteVectorStore)


def test_sqlite_vector_store_persists_between_instances(tmp_path) -> None:
    db_path = tmp_path / "vectors.sqlite"
    config = VectorStoreConfig(sqlite_path=str(db_path))
    store = build_vector_store(config)
    assert isinstance(store, SqliteVectorStore)
    store.upsert(
        "nodes",
        [VectorRecord(id="A", vector=(0.5, 0.5), metadata={"node_id": "A"}, score=0.7)],
    )
    # Re-open to ensure persistence
    store = build_vector_store(config)
    results = store.query("nodes", (0.5, 0.5), top_k=1)
    assert results and results[0].id == "A"
    assert Path(db_path).exists()
