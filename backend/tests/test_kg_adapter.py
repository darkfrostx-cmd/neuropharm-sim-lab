from backend.graph.models import (
    BiolinkEntity,
    BiolinkPredicate,
    Edge,
    Evidence,
    Node,
)
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService
from backend.simulation.kg_adapter import GraphBackedReceptorAdapter


def _build_adapter() -> tuple[GraphBackedReceptorAdapter, GraphService]:
    store = InMemoryGraphStore()
    service = GraphService(store=store)
    adapter = GraphBackedReceptorAdapter(service)

    nodes = [
        Node(id="CHEMBL:25", name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE),
        Node(id="HGNC:HTR1A", name="HTR1A", category=BiolinkEntity.GENE),
        Node(id="UBERON:0000955", name="Hippocampus", category=BiolinkEntity.BRAIN_REGION),
    ]
    edges = [
        Edge(
            subject="CHEMBL:25",
            predicate=BiolinkPredicate.INTERACTS_WITH,
            object="HGNC:HTR1A",
            confidence=0.8,
            evidence=[Evidence(source="ChEMBL", reference="PMID:1", confidence=0.85)],
            qualifiers={"affinity": 0.8},
        ),
        Edge(
            subject="UBERON:0000955",
            predicate=BiolinkPredicate.EXPRESSES,
            object="HGNC:HTR1A",
            confidence=0.6,
            evidence=[Evidence(source="AllenAtlas", reference="PMID:2", confidence=0.7)],
            qualifiers={"expression": 0.7},
        ),
    ]
    service.persist(nodes, edges)
    adapter.clear_cache()
    return adapter, service


def test_adapter_combines_interactions_and_expression():
    adapter, _ = _build_adapter()
    bundle = adapter.derive("5-HT1A", fallback_weight=0.3, fallback_evidence=0.4)

    assert bundle.kg_weight > 0.3
    assert bundle.affinity is not None and bundle.expression is not None
    assert "ChEMBL" in bundle.evidence_sources


def test_adapter_cache_invalidated_on_new_edges():
    adapter, service = _build_adapter()
    initial = adapter.derive("5-HT1A", fallback_weight=0.3, fallback_evidence=0.4)

    extra_edge = Edge(
        subject="CHEMBL:25",
        predicate=BiolinkPredicate.INTERACTS_WITH,
        object="HGNC:HTR1A",
        confidence=0.9,
        evidence=[Evidence(source="BindingDB", reference="PMID:3", confidence=0.9)],
    )
    service.persist([], [extra_edge])
    adapter.invalidate("5-HT1A")
    updated = adapter.derive("5-HT1A", fallback_weight=0.3, fallback_evidence=0.4)

    assert updated.evidence_count > initial.evidence_count
    assert "BindingDB" in updated.evidence_sources


def test_adapter_discovers_numeric_hgnc_aliases():
    store = InMemoryGraphStore()
    service = GraphService(store=store)
    adapter = GraphBackedReceptorAdapter(service)

    nodes = [
        Node(id="CHEMBL:25", name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE),
        Node(id="HGNC:5293", name="HTR2A", category=BiolinkEntity.GENE),
    ]
    edges = [
        Edge(
            subject="CHEMBL:25",
            predicate=BiolinkPredicate.INTERACTS_WITH,
            object="HGNC:5293",
            confidence=0.75,
            evidence=[Evidence(source="ChEMBL", reference="PMID:4", confidence=0.8)],
        )
    ]
    service.persist(nodes, edges)
    adapter.clear_cache()

    identifiers = adapter.identifiers_for("5-HT2A")
    assert "HGNC:5293" in identifiers

    bundle = adapter.derive("5-HT2A", fallback_weight=0.25, fallback_evidence=0.3)
    assert bundle.evidence_count >= 1
    assert bundle.kg_weight > 0.25
