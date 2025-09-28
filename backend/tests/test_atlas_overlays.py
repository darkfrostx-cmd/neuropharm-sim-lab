from backend.atlas import AtlasOverlayService
from backend.graph.models import BiolinkEntity, Node
from backend.graph.persistence import InMemoryGraphStore
from backend.graph.service import GraphService


def _service_with_node(node: Node) -> AtlasOverlayService:
    store = InMemoryGraphStore()
    store.upsert_nodes([node])
    service = GraphService(store=store)
    return AtlasOverlayService(service)


def test_curated_overlay_matches_known_region():
    node = Node(
        id="UBERON:0002421",
        name="Hippocampus",
        category=BiolinkEntity.BRAIN_REGION,
        provided_by="Curated",
        synonyms=["hippocampal formation"],
        attributes={"synonyms": ["Hippocampus", "hippocampal formation"]},
    )
    overlay_service = _service_with_node(node)
    overlay = overlay_service.lookup(node.id)
    assert overlay.provider.lower().startswith("harvard-oxford")
    assert len(overlay.coordinates) >= 2
    assert all(coord.source == "curated" for coord in overlay.coordinates)
    assert any(volume.format == "nii.gz" for volume in overlay.volumes)


def test_unknown_region_returns_empty_overlay():
    node = Node(
        id="TXT:UNKNOWN",
        name="Hypothetical Region",
        category=BiolinkEntity.NAMED_THING,
        provided_by="Synthetic",
    )
    overlay_service = _service_with_node(node)
    overlay = overlay_service.lookup(node.id)
    assert overlay.provider == "Synthetic"
    assert overlay.coordinates == []
    assert overlay.volumes == []
