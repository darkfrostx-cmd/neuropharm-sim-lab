from pathlib import Path

from backend.graph.ingest_pdsp import PDSPKiClient, PDSPKiIngestion
from backend.graph.models import BiolinkPredicate


def test_pdsp_ingestion_transforms_records():
    dataset = Path("backend/graph/data/pdsp_ki_sample.tsv")
    assert dataset.exists(), "Sample PDSP dataset should be bundled with the repository"
    client = PDSPKiClient(dataset_path=dataset)
    ingestion = PDSPKiIngestion(client=client)
    record = next(iter(client.iter_affinities(limit=1)))
    nodes, edges = ingestion.transform(record)
    assert nodes and edges
    ligand_node = next(node for node in nodes if node.id.startswith("PDSP:"))
    target_node = next(
        node
        for node in nodes
        if (
            node.id.startswith("UniProt:")
            or node.name.startswith(record.target)
            or node.attributes.get("uniprot") == record.uniprot
        )
    )
    edge = edges[0]
    assert edge.subject == ligand_node.id
    assert edge.object == target_node.id
    assert edge.predicate == BiolinkPredicate.INTERACTS_WITH
    assert edge.evidence
    annotations = edge.evidence[0].annotations
    assert annotations.get("assay") == "binding"
    if record.ki_nm is not None:
        assert annotations.get("ki") == record.ki_nm
