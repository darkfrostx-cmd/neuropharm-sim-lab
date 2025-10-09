"""Core data models for the knowledge graph.

The classes defined here closely follow the LinkML mix-in style used by the
Biolink model.  They expose ``as_linkml`` helpers so the ingest pipeline can
serialise nodes/edges in a format that downstream tools (Neo4j, Arango, BEL
export) understand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, Iterable, List, MutableMapping, Optional


class BiolinkEntity(str, Enum):
    """Supported Biolink categories."""

    NAMED_THING = "biolink:NamedThing"
    GENE = "biolink:Gene"
    CHEMICAL_SUBSTANCE = "biolink:ChemicalSubstance"
    DISEASE = "biolink:Disease"
    ANATOMICAL_ENTITY = "biolink:AnatomicalEntity"
    PHENOTYPIC_FEATURE = "biolink:PhenotypicFeature"
    PUBLICATION = "biolink:Publication"
    CELL = "biolink:Cell"
    BRAIN_REGION = "biolink:BrainRegion"
    PATHWAY = "biolink:Pathway"
    PERSON = "biolink:Person"


class BiolinkPredicate(str, Enum):
    """Subset of Biolink predicates used by the ingestion jobs."""

    RELATED_TO = "biolink:related_to"
    TREATS = "biolink:treats"
    AFFECTS = "biolink:affects"
    EXPRESSES = "biolink:expresses"
    INTERACTS_WITH = "biolink:interacts_with"
    CONTRIBUTES_TO = "biolink:contributes_to"
    COEXPRESSION_WITH = "biolink:coexpressed_with"
    LOCATED_IN = "biolink:located_in"
    ASSOCIATED_WITH = "biolink:associated_with"
    PART_OF = "biolink:part_of"
    POSITIVELY_REGULATES = "biolink:positively_regulates"


PREFIX_PATTERNS: dict[BiolinkEntity, tuple[str, ...]] = {
    BiolinkEntity.GENE: ("HGNC", "NCBIGene", "ENSEMBL", "ENSG"),
    BiolinkEntity.CHEMICAL_SUBSTANCE: ("CHEMBL", "DRUGBANK", "BINDINGDB", "PUBCHEM"),
    BiolinkEntity.DISEASE: ("MONDO", "DOID", "EFO"),
    BiolinkEntity.ANATOMICAL_ENTITY: ("UBERON", "BIRNLEX", "MBA"),
    BiolinkEntity.BRAIN_REGION: ("UBERON", "MBA", "EBRAINS"),
    BiolinkEntity.PHENOTYPIC_FEATURE: ("HP", "MP"),
    BiolinkEntity.PUBLICATION: ("PMID", "DOI"),
    BiolinkEntity.PERSON: ("ORCID", "OPENALEX"),
}


@dataclass(slots=True)
class Evidence:
    """Evidence supporting an edge."""

    source: str
    reference: Optional[str] = None
    confidence: Optional[float] = None
    uncertainty: Optional[str] = None
    annotations: MutableMapping[str, Any] = field(default_factory=dict)

    def as_linkml(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "reference": self.reference,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "annotations": dict(self.annotations),
        }


@dataclass(slots=True)
class Node:
    """Representation of a Biolink node."""

    id: str
    name: str
    category: BiolinkEntity = BiolinkEntity.NAMED_THING
    description: Optional[str] = None
    provided_by: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    xrefs: List[str] = field(default_factory=list)
    attributes: MutableMapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = normalize_identifier(self.category, self.id)
        self.xrefs = [normalize_curie(xref) for xref in self.xrefs]

    def as_linkml(self) -> dict[str, Any]:
        """Return a LinkML-compatible dict representation."""

        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "provided_by": self.provided_by,
            "synonym": list(self.synonyms),
            "xref": list(self.xrefs),
            "attributes": dict(self.attributes),
        }


@dataclass(slots=True)
class Edge:
    """Representation of a Biolink edge with attached evidence."""

    subject: str
    predicate: BiolinkPredicate
    object: str
    relation: str = "biolink:related_to"
    knowledge_level: Optional[str] = None
    confidence: Optional[float] = None
    publications: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    qualifiers: MutableMapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.subject = normalize_curie(self.subject)
        self.object = normalize_curie(self.object)
        self.publications = [normalize_identifier(BiolinkEntity.PUBLICATION, pub) for pub in self.publications]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate.value, self.object)

    def as_linkml(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate.value,
            "object": self.object,
            "relation": self.relation,
            "knowledge_level": self.knowledge_level,
            "confidence": self.confidence,
            "publications": list(self.publications),
            "evidence": [ev.as_linkml() for ev in self.evidence],
            "qualifiers": dict(self.qualifiers),
            "created_at": self.created_at.isoformat(),
        }


def normalize_identifier(category: BiolinkEntity, identifier: str) -> str:
    """Normalise identifiers into CURIE form."""

    identifier = identifier.strip()
    if not identifier:
        raise ValueError("Empty identifier")
    if identifier.lower().startswith("http") and category == BiolinkEntity.PUBLICATION:
        return identifier
    if ":" in identifier and not identifier.lower().startswith("http"):
        prefix, local_id = identifier.split(":", 1)
        prefix = prefix.strip().upper()
        local_id = local_id.strip()
        simplified = local_id.replace("-", "").replace("_", "")
        if simplified.isalnum():
            local_id = local_id.upper()
        return f"{prefix}:{local_id}"
    patterns = PREFIX_PATTERNS.get(category)
    if patterns:
        upper_identifier = identifier.upper()
        for prefix in patterns:
            prefix_upper = prefix.upper()
            if upper_identifier.startswith(prefix_upper):
                remainder = identifier[len(prefix) :]
                remainder = remainder.lstrip(": -_")
                remainder = remainder.strip()
                if remainder:
                    simplified = remainder.replace("-", "").replace("_", "")
                    local_id = remainder.upper() if simplified.isalnum() else remainder
                    return f"{prefix_upper}:{local_id}"
        if category == BiolinkEntity.PUBLICATION and identifier.isdigit():
            return f"PMID:{identifier}"
    allowed_punctuation = "-._/"
    cleaned = re.sub(rf"[^A-Za-z0-9{re.escape(allowed_punctuation)}]+", "_", identifier)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    default_prefix = PREFIX_PATTERNS.get(category, ("NEUROPHARM",))[0]
    if not cleaned:
        cleaned = identifier.replace(":", "_").strip()
    return f"{default_prefix}:{cleaned}".upper()


def normalize_curie(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Empty CURIE")
    if value.lower().startswith("http"):
        return value
    if ":" in value:
        prefix, local_id = value.split(":", 1)
        return f"{prefix.upper()}:{local_id}"
    return value.upper()


def merge_evidence(existing: Iterable[Evidence], new: Iterable[Evidence]) -> list[Evidence]:
    """Merge evidence lists, deduplicating by (source, reference)."""

    seen: dict[tuple[str, Optional[str]], Evidence] = {}
    for evidence in list(existing) + list(new):
        key = (evidence.source, evidence.reference)
        if key in seen:
            base = seen[key]
            if evidence.confidence is not None:
                base.confidence = (
                    evidence.confidence
                    if base.confidence is None
                    else max(base.confidence, evidence.confidence)
                )
            base.annotations.update(evidence.annotations)
        else:
            seen[key] = Evidence(
                source=evidence.source,
                reference=evidence.reference,
                confidence=evidence.confidence,
                uncertainty=evidence.uncertainty,
                annotations=dict(evidence.annotations),
            )
    return list(seen.values())
