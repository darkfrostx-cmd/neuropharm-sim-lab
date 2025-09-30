from backend.graph.evidence_quality import EvidenceQualityScorer
from backend.graph.models import BiolinkPredicate, Edge, Evidence


def _make_edge(*evidence: Evidence) -> Edge:
    return Edge(
        subject="CHEMBL:25",
        predicate=BiolinkPredicate.INTERACTS_WITH,
        object="HGNC:HTR1A",
        evidence=list(evidence),
    )


def test_human_evidence_outweighs_animal():
    scorer = EvidenceQualityScorer()
    human = Evidence(source="ChEMBL", annotations={"species": "Homo sapiens"})
    rodent = Evidence(source="ChEMBL", annotations={"species": "rat"})
    summary = scorer.summarise_edge(_make_edge(human, rodent))
    assert summary.has_human_data is True
    assert summary.has_animal_data is True
    assert summary.species_distribution["human"] == 1
    human_score = scorer.score_evidence(human).total_score
    rodent_score = scorer.score_evidence(rodent).total_score
    assert human_score > rodent_score


def test_chronicity_boosts_quality():
    scorer = EvidenceQualityScorer()
    acute = Evidence(source="BindingDB", annotations={"chronicity": "acute", "species": "human"})
    chronic = Evidence(source="BindingDB", annotations={"chronicity": "chronic", "species": "human"})
    acute_score = scorer.score_evidence(acute).total_score
    chronic_score = scorer.score_evidence(chronic).total_score
    assert chronic_score > acute_score


def test_provenance_weighting_prefers_referenced_studies():
    scorer = EvidenceQualityScorer()
    with_reference = Evidence(source="PDSP", reference="PMID:12345", annotations={"species": "human"})
    without_reference = Evidence(source="PDSP", annotations={"species": "human"})
    with_score = scorer.score_evidence(with_reference).total_score
    without_score = scorer.score_evidence(without_reference).total_score
    assert with_score > without_score
    edge = _make_edge(with_reference)
    summary = scorer.summarise_edge(edge)
    assert summary.score is not None and summary.score >= with_score * 0.9
