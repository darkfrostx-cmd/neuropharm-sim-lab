"""BEL export helpers."""

from __future__ import annotations

from typing import Mapping

from .models import BiolinkEntity, BiolinkPredicate, Edge, Node


PREDICATE_TO_BEL = {
    BiolinkPredicate.RELATED_TO: "--",
    BiolinkPredicate.TREATS: "->",
    BiolinkPredicate.AFFECTS: "=>",
    BiolinkPredicate.INTERACTS_WITH: "-|",
    BiolinkPredicate.CONTRIBUTES_TO: "=>",
    BiolinkPredicate.COEXPRESSION_WITH: "=",
    BiolinkPredicate.LOCATED_IN: "::",
    BiolinkPredicate.ASSOCIATED_WITH: "--",
    BiolinkPredicate.PART_OF: "partOf",
    BiolinkPredicate.EXPRESSES: "=>",
}

CATEGORY_TO_BEL = {
    BiolinkEntity.GENE: "g",
    BiolinkEntity.CHEMICAL_SUBSTANCE: "a",
    BiolinkEntity.DISEASE: "path",
    BiolinkEntity.ANATOMICAL_ENTITY: "bp",
    BiolinkEntity.BRAIN_REGION: "bp",
    BiolinkEntity.PHENOTYPIC_FEATURE: "bp",
    BiolinkEntity.PUBLICATION: "pub",
    BiolinkEntity.PERSON: "auth",
    BiolinkEntity.PATHWAY: "path",
}


def node_to_bel(node: Node) -> str:
    """Render a BEL term for the given node."""

    namespace = CATEGORY_TO_BEL.get(node.category, "a")
    label = node.name.replace("\"", "'")
    return f"{namespace}(\"{label}\")"


def edge_to_bel(edge: Edge, nodes: Mapping[str, Node]) -> str:
    """Render a BEL statement for an edge."""

    subject_node = nodes.get(edge.subject)
    object_node = nodes.get(edge.object)
    if subject_node is None or object_node is None:
        raise KeyError("Both subject and object nodes must be provided")
    predicate = PREDICATE_TO_BEL.get(edge.predicate, "--")
    evidence_note = ""
    if edge.evidence:
        references = [ev.reference for ev in edge.evidence if ev.reference]
        if references:
            evidence_note = f" // evidence: {', '.join(references)}"
    return f"{node_to_bel(subject_node)} {predicate} {node_to_bel(object_node)}{evidence_note}"

