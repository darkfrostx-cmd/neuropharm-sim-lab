from backend.graph.models import BiolinkPredicate, Node, BiolinkEntity
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
    affects_edges = [edge for edge in edges if edge.predicate == BiolinkPredicate.AFFECTS]
    assert len(affects_edges) == 2
    assert any("activates" in edge.qualifiers.get("source_sentence", "").lower() for edge in affects_edges)
    assert any("inhibits" in edge.qualifiers.get("source_sentence", "").lower() for edge in affects_edges)

