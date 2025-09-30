from backend.graph.ingest_openalex import OpenAlexIngestion
from backend.graph.ingest_chembl import (
    BindingDBIngestion,
    ChEMBLIngestion,
)
from backend.graph.ingest_indra import IndraIngestion
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.models import BiolinkPredicate


class StubOpenAlexClient:
    def iter_works(self, concept=None, search=None, per_page=25):  # noqa: D401 - match interface
        yield {
            "id": "https://openalex.org/W1",
            "display_name": "Serotonin transporters in ADHD",
            "doi": "10.1000/example",
            "publication_year": 2024,
            "cited_by_count": 5,
            "fulltext_tei": """
                <TEI><text><body><p>Serotonin activates BDNF signalling in the prefrontal cortex.</p></body></text></TEI>
            """,
            "authorships": [
                {
                    "author": {"orcid": "0000-0002-1825-0097", "display_name": "Doe, J."},
                    "author_position": "first",
                }
            ],
            "concepts": [
                {"id": "https://openalex.org/C1", "display_name": "Serotonin", "score": 0.9}
            ],
        }


class StubChEMBLClient:
    def iter_interactions(self, limit=100):  # noqa: D401
        yield {
            "molecule_chembl_id": "CHEMBL25",
            "molecule_pref_name": "Sertraline",
            "target_chembl_id": "CHEMBL1957",
            "target_pref_name": "SLC6A4",
            "document_chembl_id": "CHEMBL_DOC",
            "pchembl_value": "7.5",
            "standard_relation": "=",
            "target_organism": "Homo sapiens",
            "assay_type": "Binding",
            "assay_description": "Acute binding assay in human cortical tissue",
        }


class StubBindingDBClient:
    def iter_interactions(self, ligand, limit=50):  # noqa: D401
        yield {
            "LigandName": ligand,
            "TargetAccession": "P31645",
            "TargetName": "SLC6A4",
            "PMID": "12345",
            "Ki": 5.2,
            "TargetSpecies": "Rattus norvegicus",
        }


class StubIndraClient:
    def iter_statements(self, agent, limit=100):  # noqa: D401
        yield {
            "type": "Activation",
            "belief": 0.73,
            "subject": {"name": "HTR2A", "db_refs": {"HGNC": "HGNC:5293"}},
            "object": {"name": "GNAQ", "db_refs": {"HGNC": "HGNC:4381"}},
            "evidence": [
                {
                    "pmid": "55555",
                    "annotations": {
                        "belief": 0.73,
                        "species": "mouse",
                        "timecourse": "chronic",
                        "experiment_type": "in vivo",
                    },
                },
            ],
        }


def test_openalex_ingestion_creates_publication_and_author():
    store = InMemoryGraphStore()
    ingestion = OpenAlexIngestion(client=StubOpenAlexClient())
    report = ingestion.run(store)
    assert report.records_processed == 1
    edges = store.get_edge_evidence()
    assert any(edge.predicate == BiolinkPredicate.CONTRIBUTES_TO for edge in edges)
    # ensure DOI preserved in evidence annotations
    evidence_refs = [ev.reference for edge in edges for ev in edge.evidence if ev.reference]
    assert "10.1000/example" in evidence_refs
    mined_edges = [edge for edge in edges if edge.predicate == BiolinkPredicate.AFFECTS]
    assert mined_edges, "text-mining pipeline should add AFFECTS relation"
    assert any(edge.subject.startswith("CHEBI:") for edge in mined_edges)


def test_chembl_ingestion_interaction():
    store = InMemoryGraphStore()
    ingestion = ChEMBLIngestion(client=StubChEMBLClient())
    ingestion.run(store)
    edges = store.get_edge_evidence()
    interaction_edges = [edge for edge in edges if edge.predicate == BiolinkPredicate.INTERACTS_WITH]
    assert interaction_edges
    evidence = interaction_edges[0].evidence[0]
    assert evidence.annotations["relation"] == "="
    assert evidence.annotations["species"] == "human"
    assert evidence.annotations["design"] == "in_vitro"


def test_bindingdb_ingestion_interaction():
    store = InMemoryGraphStore()
    ingestion = BindingDBIngestion(client=StubBindingDBClient(), ligand="CHEMBL25")
    ingestion.run(store)
    edges = store.get_edge_evidence(predicate=BiolinkPredicate.INTERACTS_WITH.value)
    assert edges
    evidence = edges[0].evidence[0]
    assert evidence.reference == "PMID:12345"
    assert evidence.annotations["species"] == "rat"
    assert evidence.annotations["design"] == "in_vitro"


def test_indra_ingestion_affects_relation():
    store = InMemoryGraphStore()
    ingestion = IndraIngestion(client=StubIndraClient(), agent="HTR2A")
    ingestion.run(store)
    edges = store.get_edge_evidence(predicate=BiolinkPredicate.AFFECTS.value)
    assert edges
    edge = edges[0]
    assert edge.confidence == 0.73
    assert edge.publications == ["PMID:55555"]
    assert edge.evidence[0].annotations["species"] == "mouse"
    assert edge.evidence[0].annotations["chronicity"] == "chronic"
    assert edge.evidence[0].annotations["design"] == "in_vivo"
