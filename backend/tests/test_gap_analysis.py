from __future__ import annotations

from typing import List

from backend.graph.gaps import GapReport
from backend.graph.models import BiolinkEntity, BiolinkPredicate, Edge, Evidence, Node
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService


class StubOpenAlexClient:
    def iter_works(self, concept: str | None = None, search: str | None = None, per_page: int = 25):
        yield {
            "id": "https://openalex.org/W123",
            "display_name": "HTR2A modulation improves anxiety behaviour",
            "publication_year": 2022,
        }
        yield {
            "id": "https://openalex.org/W456",
            "display_name": "Serotonin receptor signalling case study",
            "publication_year": 2021,
        }


def build_gap_store() -> tuple[InMemoryGraphStore, str, str, str]:
    store = InMemoryGraphStore()
    receptor = Node(
        id="HGNC:6",
        name="HTR2A",
        category=BiolinkEntity.GENE,
        attributes={
            "causal_samples": [
                {"target": "HP:0000729", "treatment": 0.0, "outcome": 0.1},
                {"target": "HP:0000729", "treatment": 1.0, "outcome": 0.9},
                {"target": "HP:0000729", "treatment": 0.5, "outcome": 0.4},
                {"target": "HP:0000729", "treatment": 1.2, "outcome": 1.0},
            ]
        },
    )
    behaviour = Node(
        id="HP:0000729",
        name="Anxiety",
        category=BiolinkEntity.PHENOTYPIC_FEATURE,
    )
    drug = Node(
        id="CHEMBL:25",
        name="Sertraline",
        category=BiolinkEntity.CHEMICAL_SUBSTANCE,
    )
    region = Node(
        id="UBERON:0001950",
        name="Cerebral cortex",
        category=BiolinkEntity.ANATOMICAL_ENTITY,
    )
    other_behaviour = Node(
        id="HP:0000739",
        name="Irritability",
        category=BiolinkEntity.PHENOTYPIC_FEATURE,
    )
    store.upsert_nodes([receptor, behaviour, drug, region, other_behaviour])
    edges: List[Edge] = [
        Edge(
            subject=drug.id,
            predicate=BiolinkPredicate.INTERACTS_WITH,
            object=receptor.id,
            confidence=0.85,
            evidence=[Evidence(source="ChEMBL", reference="PMID:111")],
        ),
        Edge(
            subject=receptor.id,
            predicate=BiolinkPredicate.EXPRESSES,
            object=region.id,
            confidence=0.65,
            evidence=[Evidence(source="GTEx", reference="PMID:222")],
        ),
        Edge(
            subject=region.id,
            predicate=BiolinkPredicate.RELATED_TO,
            object=behaviour.id,
            confidence=0.6,
            evidence=[Evidence(source="NeuroSynth", reference="PMID:333")],
        ),
        Edge(
            subject=drug.id,
            predicate=BiolinkPredicate.AFFECTS,
            object=behaviour.id,
            confidence=0.72,
            qualifiers={"target": behaviour.id, "treatment_value": 1.0, "outcome_value": 0.7},
            evidence=[Evidence(source="ClinicalTrial", reference="PMID:444")],
        ),
        Edge(
            subject=receptor.id,
            predicate=BiolinkPredicate.RELATED_TO,
            object=other_behaviour.id,
            confidence=0.4,
            evidence=[Evidence(source="OpenAlex", reference="10.1000/example")],
        ),
    ]
    store.upsert_edges(edges)
    return store, receptor.id, behaviour.id, drug.id


def test_embedding_gap_predictions_rank_expected_edge() -> None:
    store, receptor_id, behaviour_id, _ = build_gap_store()
    service = GraphService(store=store, literature_client=StubOpenAlexClient())
    reports = service.find_gaps([receptor_id, behaviour_id], top_k=5)
    assert reports
    target_report = next(report for report in reports if report.subject == receptor_id and report.object == behaviour_id)
    assert isinstance(target_report, GapReport)
    assert target_report.embedding_score < 0
    assert target_report.predicate == BiolinkPredicate.AFFECTS
    assert reports.index(target_report) <= 3
    assert target_report.metadata.get("context_weight") is not None
    assert "context_label" in target_report.metadata


def test_gap_report_includes_causal_summary_and_literature() -> None:
    store, receptor_id, behaviour_id, _ = build_gap_store()
    service = GraphService(store=store, literature_client=StubOpenAlexClient())
    reports = service.find_gaps([receptor_id, behaviour_id], top_k=5)
    report = next(report for report in reports if report.subject == receptor_id and report.object == behaviour_id)
    assert report.causal_direction == "increase"
    assert report.causal_effect is not None and report.causal_effect > 0
    assert report.causal_confidence is not None and report.causal_confidence > 0.5
    assert report.counterfactual_summary is not None and receptor_id in report.counterfactual_summary
    assert report.literature and "openalex.org/W123" in report.literature[0]
    assert report.metadata.get("context_weight")
