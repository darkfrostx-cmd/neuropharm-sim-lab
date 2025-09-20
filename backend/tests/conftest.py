import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

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
import backend.main as backend_main


@pytest.fixture()
def serotonin_graph(monkeypatch: pytest.MonkeyPatch) -> tuple[GraphService, GraphBackedReceptorAdapter]:
    """Seed the in-memory knowledge graph with representative receptor edges."""

    store = InMemoryGraphStore()
    service = GraphService(store=store)
    adapter = GraphBackedReceptorAdapter(service)

    monkeypatch.setattr(backend_main, "GRAPH_SERVICE", service)
    monkeypatch.setattr(backend_main, "KG_ADAPTER", adapter)

    nodes = [
        Node(id="CHEMBL:25", name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE),
        Node(id="HGNC:HTR1A", name="HTR1A", category=BiolinkEntity.GENE),
        Node(id="HGNC:HTR2A", name="HTR2A", category=BiolinkEntity.GENE),
        Node(id="UBERON:0000955", name="Hippocampus", category=BiolinkEntity.BRAIN_REGION),
    ]
    edges = [
        Edge(
            subject="CHEMBL:25",
            predicate=BiolinkPredicate.INTERACTS_WITH,
            object="HGNC:HTR1A",
            confidence=0.82,
            evidence=[Evidence(source="ChEMBL", reference="PMID:1", confidence=0.88)],
            qualifiers={"affinity": 0.83},
        ),
        Edge(
            subject="CHEMBL:25",
            predicate=BiolinkPredicate.INTERACTS_WITH,
            object="HGNC:HTR2A",
            confidence=0.45,
            evidence=[Evidence(source="ChEMBL", reference="PMID:2", confidence=0.5)],
        ),
        Edge(
            subject="UBERON:0000955",
            predicate=BiolinkPredicate.EXPRESSES,
            object="HGNC:HTR1A",
            confidence=0.68,
            evidence=[Evidence(source="AllenAtlas", reference="PMID:3", confidence=0.7)],
            qualifiers={"expression": 0.72},
        ),
        Edge(
            subject="UBERON:0000955",
            predicate=BiolinkPredicate.EXPRESSES,
            object="HGNC:HTR2A",
            confidence=0.32,
            evidence=[Evidence(source="AllenAtlas", reference="PMID:4", confidence=0.35)],
        ),
        Edge(
            subject="HGNC:HTR1A",
            predicate=BiolinkPredicate.COEXPRESSION_WITH,
            object="HGNC:HTR2A",
            confidence=0.4,
            evidence=[Evidence(source="CoExp", reference="PMID:5", confidence=0.42)],
            qualifiers={"weight": 0.38},
        ),
    ]
    service.persist(nodes, edges)
    adapter.clear_cache()

    return service, adapter
