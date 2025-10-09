from backend.atlas import AtlasOverlayService
from backend.atlas.assets import load_hcp_reference, load_julich_reference
from backend.atlas.qa import run_geometry_qa, validate_overlay_geometry
from backend.graph.models import BiolinkEntity, Node
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService


def _service_with(nodes):
    store = InMemoryGraphStore()
    store.upsert_nodes(nodes)
    return AtlasOverlayService(GraphService(store=store))


def test_hcp_reference_overlay_passes_geometry_checks():
    reference = load_hcp_reference()
    region = reference["regions"][0]
    node = Node(
        id=region["id"],
        name=region["name"],
        category=BiolinkEntity.BRAIN_REGION,
        provided_by="Human Connectome Project",
        attributes={"synonyms": [region["name"]]},
    )
    service = _service_with([node])
    overlay = service.lookup(node.id)
    assert validate_overlay_geometry(overlay) == []


def test_geometry_qa_collects_julich_overlays():
    reference = load_julich_reference()
    region = reference["regions"][0]
    node = Node(
        id=region["id"],
        name=region["name"],
        category=BiolinkEntity.BRAIN_REGION,
        provided_by="Julich-Brain",
        attributes={"synonyms": [region["name"]]},
    )
    service = _service_with([node])
    overlay = service.lookup(node.id)
    results = run_geometry_qa([overlay])
    assert node.id not in results
