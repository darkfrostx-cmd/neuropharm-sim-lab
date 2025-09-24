"""Lightweight entity grounding helpers for the text-mining pipeline.

The blueprint expects text-mined entities to resolve to persistent identifiers
instead of the hash-based placeholders used during the initial scaffolding.
The :class:`GroundingResolver` below provides a deterministic fallback that
works entirely offline while leaving room for richer integrations when
scispaCy/INDRA stacks are available.

The resolver consults a curated synonym table for high-value neuropharmacology
terms and falls back to heuristics for common identifier patterns (HGNC gene
symbols, CHEBI compounds, and basic anatomy labels).  Each grounding attempt
returns a :class:`GroundedEntity` with an estimated confidence so downstream
code can surface the provenance to curators.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
import re
from typing import Dict, Mapping, Tuple

from .models import BiolinkEntity


@dataclass(frozen=True)
class GroundedEntity:
    """Representation of a grounded mention."""

    id: str
    name: str
    category: BiolinkEntity
    confidence: float
    synonyms: Tuple[str, ...] = ()
    xrefs: Tuple[str, ...] = ()
    provenance: Mapping[str, object] = None  # type: ignore[assignment]


class GroundingResolver:
    """Resolve free-text mentions to Biolink nodes."""

    def __init__(self, *, synonym_table: Mapping[str, Mapping[str, object]] | None = None) -> None:
        if synonym_table is None:
            synonym_table = _load_default_synonyms()
        self._synonyms = self._normalise_synonym_table(synonym_table)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def resolve(self, mention: str) -> GroundedEntity:
        mention = mention.strip()
        if not mention:
            raise ValueError("Empty mention cannot be grounded")

        lookup_key = mention.lower()
        if lookup_key in self._synonyms:
            record = self._synonyms[lookup_key]
            return GroundedEntity(
                id=record["id"],
                name=record["label"],
                category=record["category"],
                confidence=0.92,
                synonyms=tuple(record.get("synonyms", ())),
                xrefs=tuple(record.get("xrefs", ())),
                provenance={"strategy": "curated"},
            )

        heuristic = self._heuristic_ground(mention)
        if heuristic is not None:
            return heuristic

        placeholder_id = f"TXT:{_slugify(mention)}"
        return GroundedEntity(
            id=placeholder_id,
            name=mention,
            category=BiolinkEntity.NAMED_THING,
            confidence=0.35,
            synonyms=(mention,),
            provenance={"strategy": "fallback"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _heuristic_ground(self, mention: str) -> GroundedEntity | None:
        token = mention.strip()
        upper = token.upper()

        # HGNC symbols are typically uppercase and <= 8 characters.
        if 2 <= len(upper) <= 8 and upper.isalnum() and upper == token:
            return GroundedEntity(
                id=f"HGNC:{upper}",
                name=token,
                category=BiolinkEntity.GENE,
                confidence=0.65,
                synonyms=(token,),
                provenance={"strategy": "heuristic_gene"},
            )

        # CHEBI identifiers often appear as CHEBI:#### or compound names ending with ine/ol.
        if upper.startswith("CHEBI:"):
            return GroundedEntity(
                id=upper,
                name=mention,
                category=BiolinkEntity.CHEMICAL_SUBSTANCE,
                confidence=0.7,
                synonyms=(mention,),
                provenance={"strategy": "heuristic_chebi"},
            )

        if re.search(r"(ine|ol|ate)$", token.lower()):
            return GroundedEntity(
                id=f"CHEBI:{_slugify(token)}",
                name=token,
                category=BiolinkEntity.CHEMICAL_SUBSTANCE,
                confidence=0.55,
                synonyms=(token,),
                provenance={"strategy": "heuristic_compound"},
            )

        if "cortex" in token.lower() or "hippocampus" in token.lower():
            return GroundedEntity(
                id=f"UBERON:{_slugify(token)}",
                name=token,
                category=BiolinkEntity.BRAIN_REGION,
                confidence=0.5,
                synonyms=(token,),
                provenance={"strategy": "heuristic_region"},
            )

        return None

    @staticmethod
    def _normalise_synonym_table(
        raw: Mapping[str, Mapping[str, object]]
    ) -> Dict[str, Dict[str, object]]:
        table: Dict[str, Dict[str, object]] = {}
        for _, record in raw.items():
            label = str(record.get("label", "")).strip()
            if not label:
                continue
            category = record.get("category")
            if isinstance(category, str):
                try:
                    record_category = BiolinkEntity(category)
                except ValueError:
                    record_category = BiolinkEntity.NAMED_THING
            elif isinstance(category, BiolinkEntity):
                record_category = category
            else:
                record_category = BiolinkEntity.NAMED_THING
            entry: Dict[str, object] = {
                "id": str(record.get("id", label)),
                "label": label,
                "category": record_category,
                "synonyms": tuple(sorted({label, *record.get("synonyms", [])}, key=str.lower)),
                "xrefs": tuple(record.get("xrefs", ())),
            }
            for synonym in entry["synonyms"]:  # type: ignore[index]
                key = synonym.lower()
                table[key] = entry
        return table


def _load_default_synonyms() -> Mapping[str, Mapping[str, object]]:
    with resources.files("backend.graph.data").joinpath("grounding_synonyms.json").open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
    if not cleaned:
        cleaned = "TERM"
    return cleaned.upper()


__all__ = ["GroundedEntity", "GroundingResolver"]

