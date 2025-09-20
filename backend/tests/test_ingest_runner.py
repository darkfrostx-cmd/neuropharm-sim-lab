from backend.graph.ingest_base import BaseIngestionJob
from backend.graph.ingest_runner import (DEFAULT_SEED_PATH, IngestionPlan, bootstrap_graph, load_seed_graph)
from backend.graph.models import BiolinkEntity, BiolinkPredicate, Edge, Node
from backend.graph.service import GraphService


class DummyJob(BaseIngestionJob):
    name = "dummy"
    source = "test"

    def fetch(self, limit=None):  # noqa: D401 - test helper
        yield {"idx": 1}

    def transform(self, record):  # noqa: D401 - test helper
        node = Node(id="CHEMBL999", name="Test", category=BiolinkEntity.CHEMICAL_SUBSTANCE)
        edge = Edge(
            subject=node.id,
            predicate=BiolinkPredicate.RELATED_TO,
            object="HGNC:0001",
        )
        return [node], [edge]


def test_load_seed_graph_populates_store():
    service = GraphService()
    store = service.store
    assert not store.all_nodes()

    loaded = load_seed_graph(service, seed_path=DEFAULT_SEED_PATH)
    assert loaded
    nodes = {node.id for node in store.all_nodes()}
    assert "CHEMBL:25" in nodes
    edges = list(store.all_edges())
    assert any(edge.subject == "CHEMBL:25" for edge in edges)


def test_bootstrap_uses_plan_when_seed_disabled():
    service = GraphService()
    plan = IngestionPlan(jobs=[DummyJob()], limit=1)
    reports = bootstrap_graph(service, plan=plan, use_seed=False)
    assert reports and reports[0].records_processed == 1
    assert service.store.get_node("CHEMBL:999") is not None
