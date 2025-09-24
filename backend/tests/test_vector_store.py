from backend.config import VectorStoreConfig
from backend.graph.vector_store import InMemoryVectorStore, VectorRecord, build_vector_store


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
    assert isinstance(store, InMemoryVectorStore)
