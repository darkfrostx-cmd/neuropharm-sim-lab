from backend.graph.models import (
    BiolinkEntity,
    BiolinkPredicate,
    Edge,
    Evidence,
    Node,
)
from backend.config import GraphConfig
from backend.graph.gaps import GapReport
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService


def build_store() -> InMemoryGraphStore:
    store = InMemoryGraphStore()
    node_a = Node(id="CHEMBL:25", name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE)
    node_b = Node(id="HGNC:5", name="SLC6A4", category=BiolinkEntity.GENE)
    node_c = Node(id="HGNC:6", name="HTR2A", category=BiolinkEntity.GENE)
    store.upsert_nodes([node_a, node_b, node_c])
    edge_ab = Edge(
        subject=node_a.id,
        predicate=BiolinkPredicate.INTERACTS_WITH,
        object=node_b.id,
        confidence=0.8,
        evidence=[Evidence(source="ChEMBL", reference="PMID:1", confidence=0.8)],
    )
    edge_bc = Edge(
        subject=node_b.id,
        predicate=BiolinkPredicate.RELATED_TO,
        object=node_c.id,
        evidence=[Evidence(source="OpenAlex", reference="10.1000/example")],
    )
    store.upsert_edges([edge_ab, edge_bc])
    return store


def test_get_evidence_returns_summaries() -> None:
    store = build_store()
    service = GraphService(store=store)
    summaries = service.get_evidence(subject="CHEMBL:25")
    assert summaries
    assert summaries[0].evidence[0].source == "ChEMBL"


def test_expand_returns_fragment() -> None:
    store = build_store()
    service = GraphService(store=store)
    fragment = service.expand("HGNC:5", depth=1)
    node_ids = {node.id for node in fragment.nodes}
    assert "HGNC:5" in node_ids
    assert any(edge.predicate == BiolinkPredicate.RELATED_TO for edge in fragment.edges)


def test_find_gaps_between_focus_nodes() -> None:
    store = build_store()
    service = GraphService(store=store)
    gaps = service.find_gaps(["HGNC:5", "HGNC:6", "CHEMBL:25"], top_k=3)
    assert isinstance(gaps, list)
    assert all(isinstance(gap, GapReport) for gap in gaps)
    assert any(gap.subject == "CHEMBL:25" and gap.object == "HGNC:6" for gap in gaps)


def test_graph_config_from_env_supports_mirrors() -> None:
    env = {
        "GRAPH_BACKEND": "neo4j",
        "GRAPH_URI": "neo4j+s://primary",
        "GRAPH_USERNAME": "neo",
        "GRAPH_PASSWORD": "pass",
        "GRAPH_MIRROR_A_BACKEND": "arangodb",
        "GRAPH_MIRROR_A_URI": "https://arangodb.example", 
        "GRAPH_MIRROR_A_DATABASE": "brainos",
        "GRAPH_MIRROR_A_OPT_TLS": "true",
    }

    config = GraphConfig.from_env(env)

    assert config.backend == "neo4j"
    assert not config.is_memory_only
    assert config.primary.uri == "neo4j+s://primary"
    assert config.primary.username == "neo"
    assert len(config.mirrors) == 1
    mirror = config.mirrors[0]
    assert mirror.backend == "arangodb"
    assert mirror.uri == "https://arangodb.example"
    assert mirror.database == "brainos"
    assert mirror.options.get("tls") == "true"
