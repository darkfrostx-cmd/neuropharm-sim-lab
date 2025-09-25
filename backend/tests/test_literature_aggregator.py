from backend.graph.literature import LiteratureAggregator, LiteratureRecord
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService


class _StubClient:
    def __init__(self, records: list[LiteratureRecord]) -> None:
        self._records = records

    def search(self, query: str, *, limit: int = 5):  # type: ignore[override]
        yield from self._records[:limit]


def test_aggregator_deduplicates_and_ranks() -> None:
    record_a = LiteratureRecord(
        title="Neurotransmitter modulation",
        identifier="10.1000/a",
        year=2020,
        source="OpenAlex",
        score=50,
        snippet="Modulates dopaminergic tone",
    )
    record_b = LiteratureRecord(
        title="Neurotransmitter modulation",  # same identifier, more detail
        identifier="10.1000/a",
        year=2021,
        source="Semantic Scholar",
        score=75,
        url="https://example.org/paper",
        snippet="Detailed mechanistic insight",
    )
    record_c = LiteratureRecord(
        title="Synaptic plasticity",
        identifier="10.1000/b",
        year=2019,
        source="OpenAlex",
        score=10,
    )
    aggregator = LiteratureAggregator(clients=[_StubClient([record_a]), _StubClient([record_b, record_c])])
    results = aggregator.suggest("SLC6A4", "HTR2A", limit=5)
    assert len(results) == 2
    assert results[0].identifier == "10.1000/a"
    assert results[0].score == 75
    assert results[0].url == "https://example.org/paper"


def test_formatting_matches_expectations() -> None:
    aggregator = LiteratureAggregator(clients=[])
    record = LiteratureRecord(
        title="Causal inference in neuropharmacology",
        identifier="arXiv:1234",
        year=2023,
        source="Semantic Scholar",
        score=12,
        url="https://example.org/preprint",
    )
    formatted = LiteratureAggregator(clients=[])
    formatted_string = formatted.suggest("A", "B", limit=0)
    # Ensure aggregator with no clients gracefully returns empty suggestions
    assert formatted_string == []
    service = GraphService(store=InMemoryGraphStore(), literature=aggregator)
    assert (
        service._format_literature_record(record)
        == "Causal inference in neuropharmacology (2023) [arXiv:1234] via Semantic Scholar <https://example.org/preprint>"
    )

