import pytest

from backend.graph.bel import edge_to_bel, node_to_bel
from backend.graph.models import (
    BiolinkEntity,
    BiolinkPredicate,
    Edge,
    Evidence,
    Node,
    merge_evidence,
    normalize_identifier,
)


@pytest.mark.parametrize("raw_id", ["chembl:25", "CHEMBL25"])
def test_node_normalisation(raw_id: str) -> None:
    node = Node(id=raw_id, name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE)
    assert node.id == "CHEMBL:25"
    assert node.as_linkml()["category"] == BiolinkEntity.CHEMICAL_SUBSTANCE.value


@pytest.mark.parametrize(
    ("category", "raw", "expected"),
    [
        (BiolinkEntity.CHEMICAL_SUBSTANCE, "CHEMBL25", "CHEMBL:25"),
        (BiolinkEntity.CHEMICAL_SUBSTANCE, "drugbankdb0001", "DRUGBANK:DB0001"),
        (BiolinkEntity.CHEMICAL_SUBSTANCE, "BindingDB500501", "BINDINGDB:500501"),
        (
            BiolinkEntity.CHEMICAL_SUBSTANCE,
            "BindingDB:500501",
            "BINDINGDB:500501",
        ),
        (
            BiolinkEntity.PERSON,
            "ORCID0000-0002-1825-0097",
            "ORCID:0000-0002-1825-0097",
        ),
        (
            BiolinkEntity.PERSON,
            "0000-0002-1825-0097",
            "ORCID:0000-0002-1825-0097",
        ),
    ],
)
def test_normalize_identifier_known_prefixes(category, raw, expected) -> None:
    assert normalize_identifier(category, raw) == expected


def test_normalize_identifier_preserves_http_publications() -> None:
    identifier = "https://openalex.org/W1234567890"
    assert normalize_identifier(BiolinkEntity.PUBLICATION, identifier) == identifier


def test_edge_bel_export() -> None:
    drug = Node(id="CHEMBL:25", name="Sertraline", category=BiolinkEntity.CHEMICAL_SUBSTANCE)
    gene = Node(id="HGNC:5", name="SLC6A4", category=BiolinkEntity.GENE)
    evidence = Evidence(source="ChEMBL", reference="PMID:123", confidence=0.9)
    edge = Edge(
        subject=drug.id,
        predicate=BiolinkPredicate.INTERACTS_WITH,
        object=gene.id,
        evidence=[evidence],
    )
    bel = edge_to_bel(edge, {drug.id: drug, gene.id: gene})
    assert "Sertraline" in bel
    assert "SLC6A4" in bel
    assert "PMID:123" in bel


def test_merge_evidence() -> None:
    ev1 = Evidence(source="ChEMBL", reference="PMID:1", confidence=0.6, annotations={"assay": "binding"})
    ev2 = Evidence(source="ChEMBL", reference="PMID:1", confidence=0.8, annotations={"organism": "human"})
    merged = merge_evidence([ev1], [ev2])
    assert len(merged) == 1
    merged_ev = merged[0]
    assert merged_ev.confidence == 0.8
    assert merged_ev.annotations["assay"] == "binding"
    assert merged_ev.annotations["organism"] == "human"
