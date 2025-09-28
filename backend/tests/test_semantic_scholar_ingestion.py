import math

import pytest

from backend.graph.entity_grounding import GroundedEntity, GroundingResolver
from backend.graph.ingest_semantic_scholar import SemanticScholarIngestion
from backend.graph.literature import LiteratureRecord
from backend.graph.models import BiolinkEntity


class _StubGrounder(GroundingResolver):  # type: ignore[misc]
    mapping: dict[str, GroundedEntity]

    def __init__(self, mapping: dict[str, GroundedEntity]) -> None:
        super().__init__()
        self.mapping = mapping

    def resolve(self, mention: str) -> GroundedEntity:  # type: ignore[override]
        if mention in self.mapping:
            return self.mapping[mention]
        return super().resolve(mention)


class _StubClient:
    def __init__(self, responses: dict[str, list[LiteratureRecord]]) -> None:
        self.responses = responses
        self.requested: list[tuple[str, int]] = []

    def search(self, query: str, *, limit: int = 5):  # type: ignore[override]
        self.requested.append((query, limit))
        yield from self.responses.get(query, [])


def test_ingestion_emits_grounded_nodes_and_edges() -> None:
    record = LiteratureRecord(
        title="BDNF enables synaptic resilience",
        identifier="paper-123",
        year=2022,
        source="Semantic Scholar",
        score=48,
        url="https://example.org/paper",
        snippet="BDNF enhances TrkB-dependent plasticity in hippocampus",
    )
    client = _StubClient({"BDNF synaptic potentiation antidepressant": [record]})
    grounder = _StubGrounder(
        {
            "BDNF synaptic": GroundedEntity(
                id="HGNC:1033",
                name="BDNF",
                category=BiolinkEntity.GENE,
                confidence=0.9,
            ),
            "synaptic potentiation": GroundedEntity(
                id="GO:0060291",
                name="long-term potentiation",
                category=BiolinkEntity.PHENOTYPIC_FEATURE,
                confidence=0.8,
            ),
            "potentiation antidepressant": GroundedEntity(
                id="CHEBI:00068",
                name="antidepressant",
                category=BiolinkEntity.CHEMICAL_SUBSTANCE,
                confidence=0.7,
            ),
            "antidepressant": GroundedEntity(
                id="CHEBI:00068",
                name="antidepressant",
                category=BiolinkEntity.CHEMICAL_SUBSTANCE,
                confidence=0.7,
            ),
        }
    )
    ingestion = SemanticScholarIngestion(client=client, grounder=grounder)

    batches = list(ingestion.fetch(limit=9))
    assert len(batches) == 1
    nodes, edges = ingestion.transform(batches[0])

    publication_nodes = [node for node in nodes if node.category == BiolinkEntity.PUBLICATION]
    assert publication_nodes and publication_nodes[0].id.endswith("PAPER-123")
    assert publication_nodes[0].attributes["year"] == 2022
    assert math.isclose(publication_nodes[0].attributes["score"], 48)

    assert edges, "expected grounded edges"
    edge = edges[0]
    assert edge.subject in {node.id for node in nodes if node.category != BiolinkEntity.PUBLICATION}
    assert edge.object.endswith("PAPER-123")
    assert edge.evidence[0].annotations["url"] == "https://example.org/paper"
    assert edge.evidence[0].annotations["snippet"].startswith("BDNF")


def test_missing_queries_are_skipped(caplog: pytest.LogCaptureFixture) -> None:
    client = _StubClient({"TrkB facilitation chronic stress": []})
    grounder = _StubGrounder({})
    ingestion = SemanticScholarIngestion(client=client, grounder=grounder)

    with caplog.at_level("DEBUG"):
        batches = list(ingestion.fetch(limit=3))
    assert batches == []
    assert any("yielded no records" in message for message in caplog.messages)


def test_requires_queries() -> None:
    client = _StubClient({})
    grounder = _StubGrounder({})
    with pytest.raises(ValueError):
        SemanticScholarIngestion(client=client, queries=[], grounder=grounder)
