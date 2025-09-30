from backend.graph.models import (
    BiolinkEntity,
    BiolinkPredicate,
    Edge,
    Evidence,
    Node,
)
from backend.graph.gaps import GapReport
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService
from backend.graph.literature import LiteratureAggregator, LiteratureRecord


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


def test_literature_suggestions_use_aggregator() -> None:
    class _StubAggregator:
        def suggest(self, subject: str, target: str, *, limit: int = 5):  # type: ignore[override]
            return [
                LiteratureRecord(
                    title="Sertraline and SLC6A4 modulation",
                    identifier="PMID:12345",
                    year=2022,
                    source="Semantic Scholar",
                    score=42,
                    url="https://example.org/pmid12345",
                    snippet="Detailed analysis",
                )
            ]

    store = build_store()
    service = GraphService(store=store, literature=_StubAggregator())
    suggestions = service._suggest_literature("CHEMBL:25", "HGNC:6", limit=1)
    assert suggestions == [
        "Sertraline and SLC6A4 modulation (2022) [PMID:12345] via Semantic Scholar <https://example.org/pmid12345>"
    ]


def test_gap_reports_include_dual_source_literature() -> None:
    class _OpenAlexStub:
        def search(self, query: str, *, limit: int = 5):  # type: ignore[override]
            yield LiteratureRecord(
                title="Sertraline effects on SLC6A4",
                identifier="openalex:1",
                year=2021,
                source="OpenAlex",
                score=30,
                url="https://example.org/openalex",
            )

    class _SemanticScholarStub:
        def search(self, query: str, *, limit: int = 5):  # type: ignore[override]
            yield LiteratureRecord(
                title="Dual transporter modulation",
                identifier="semantic:1",
                year=2020,
                source="Semantic Scholar",
                score=25,
                url="https://example.org/semantic",
            )

    aggregator = LiteratureAggregator(clients=[_OpenAlexStub(), _SemanticScholarStub()])

    store = build_store()
    service = GraphService(store=store, literature=aggregator)

    gaps = service.find_gaps(["HGNC:5", "HGNC:6", "CHEMBL:25"], top_k=3)
    gap = next(gap for gap in gaps if gap.subject == "CHEMBL:25" and gap.object == "HGNC:6")

    assert any("via OpenAlex" in entry for entry in gap.literature)
    assert any("via Semantic Scholar" in entry for entry in gap.literature)

