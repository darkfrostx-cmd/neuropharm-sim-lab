from backend.graph.models import BiolinkPredicate, Node, BiolinkEntity
from backend.graph.models import BiolinkEntity, BiolinkPredicate, Node
from backend.graph.text_mining import SciSpaCyExtractor, TextMiningPipeline


def make_work_node() -> Node:
    return Node(
        id="https://openalex.org/W1",
        name="Example work",
        category=BiolinkEntity.PUBLICATION,
    )


def test_text_mining_pipeline_extracts_relations_from_inline_tei() -> None:
    pipeline = TextMiningPipeline(relation_extractor=SciSpaCyExtractor())
    record = {
        "id": "https://openalex.org/W1",
        "fulltext_tei": """
            <TEI><text><body>
                <p>Dopamine activates cAMP signalling in the striatum.</p>
                <p>Excess dopamine inhibits GABA neurons.</p>
            </body></text></TEI>
        """,
    }
    nodes, edges = pipeline.mine(record, make_work_node())
    assert nodes
    assert edges
    by_id = {node.id: node for node in nodes}
    assert "CHEBI:18243" in by_id
    assert by_id["CHEBI:18243"].category == BiolinkEntity.CHEMICAL_SUBSTANCE
    assert "CHEBI:16865" in by_id  # GABA grounding
    affects_edges = [edge for edge in edges if edge.predicate == BiolinkPredicate.AFFECTS]
    assert len(affects_edges) == 2
    first_edge = affects_edges[0]
    assert first_edge.relation in {"biolink:positively_regulates", "biolink:negatively_regulates"}
    assert "agent_grounding" in first_edge.qualifiers
    assert first_edge.evidence[0].annotations["grounding_confidence"]["agent"] > 0.5

