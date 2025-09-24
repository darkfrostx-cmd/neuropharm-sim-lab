"""Lightweight text-mining pipeline for OpenAlex records.

The project blueprint calls for a GROBID → scispaCy → INDRA chain that turns
literature hits into mechanistic graph updates.  The implementation below keeps
the moving pieces modular so deployments can plug in the real services while the
default test suite relies on pure-Python fallbacks.

``TextMiningPipeline`` exposes a small ``mine`` method that accepts an OpenAlex
work payload and returns ``Node``/``Edge`` fragments ready for persistence.  It
tries to:

* resolve a PDF (or TEI blob) for the work;
* convert the PDF into TEI via a minimal HTTP client for a running GROBID
  instance; when GROBID is unavailable the pipeline honours inline ``tei``
  fields on the payload so unit tests can inject fixtures without network I/O;
* extract candidate relations using scispaCy when the model is installed, or a
  deterministic rule-based fallback when it is not; and
* assemble the relations into Biolink-compatible nodes and edges using the
  existing evidence helpers.

The scispaCy step is intentionally defensive: the heavy spaCy models are not
available in the CI image, so we fall back to a simple regex-driven extractor
that looks for ``<agent> (activates|inhibits|modulates) <target>`` patterns.  The
resulting edges carry the original sentence as an evidence annotation so the API
can surface a provenance snippet.

When integrators stand up a real pipeline they can subclass ``RelationExtractor``
and ``TextMiningPipeline`` to inject richer entity linking and BEL/INDRA
assembly; the project only relies on the small public ``mine`` API.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import logging
import re
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple
from xml.etree import ElementTree

try:  # pragma: no cover - optional dependency
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]

from .entity_grounding import GroundedEntity, GroundingResolver
from .ingest_base import BaseIngestionJob
from .models import BiolinkEntity, BiolinkPredicate, Edge, Node


LOGGER = logging.getLogger(__name__)


RelationTuple = Tuple[str, str, str, str]


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
    if not cleaned:
        cleaned = "TERM"
    return cleaned.upper()


def _tei_to_plain_text(tei_xml: str) -> str:
    """Collapse a TEI document into whitespace-normalised plain text."""

    try:
        root = ElementTree.fromstring(tei_xml)
    except ElementTree.ParseError:  # pragma: no cover - defensive guard
        return re.sub(r"\s+", " ", tei_xml)

    text_fragments: List[str] = []
    for element in root.iter():
        if element.text:
            text_fragments.append(element.text)
        if element.tail:
            text_fragments.append(element.tail)
    merged = " ".join(fragment.strip() for fragment in text_fragments if fragment.strip())
    return re.sub(r"\s+", " ", merged)


class GrobidClient:
    """Minimal HTTP client for a running GROBID instance."""

    def __init__(self, base_url: str = "http://localhost:8070") -> None:
        if requests is None:  # pragma: no cover - optional dependency
            raise ImportError("requests is required for GrobidClient")
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def process_pdf(self, pdf_bytes: bytes, *, consolidate_citations: bool = True) -> str:
        files = {"input": ("document.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        params = {"includeRawAffiliations": "1"}
        if consolidate_citations:
            params["consolidateHeader"] = "1"
            params["consolidateCitations"] = "1"
        response = self.session.post(
            f"{self.base_url}/api/processFulltextDocument",
            files=files,
            data=params,
            timeout=120,
        )
        response.raise_for_status()
        return response.text


class RelationExtractor:
    """Base class for relation extractors operating on TEI text."""

    def extract(self, text: str) -> List[RelationTuple]:  # pragma: no cover - interface
        raise NotImplementedError


class SciSpaCyExtractor(RelationExtractor):
    """scispaCy-backed relation extractor with a regex fallback."""

    _PATTERN = re.compile(
        r"(?P<agent>[A-Z][A-Za-z0-9-]{2,})\s+(?P<verb>activates|inhibits|modulates|suppresses|enhances)\s+(?P<target>[A-Z][A-Za-z0-9-]{2,})",
        flags=re.IGNORECASE,
    )

    def __init__(self) -> None:
        try:  # pragma: no cover - optional dependency
            import spacy
            from scispacy.abbreviation import AbbreviationDetector

            self._nlp = spacy.load("en_core_sci_sm")  # type: ignore[assignment]
            self._nlp.add_pipe("sentencizer", first=True)
            self._nlp.add_pipe(AbbreviationDetector(self._nlp))
        except Exception:  # pragma: no cover - optional dependency
            self._nlp = None  # type: ignore[assignment]

    def _regex_extract(self, text: str) -> List[RelationTuple]:
        relations: List[RelationTuple] = []
        for match in self._PATTERN.finditer(text):
            agent = match.group("agent")
            verb = match.group("verb").lower()
            target = match.group("target")
            sentence = match.group(0)
            relations.append((agent, verb, target, sentence))
        return relations

    def extract(self, text: str) -> List[RelationTuple]:
        if not text:
            return []
        if self._nlp is None:
            return self._regex_extract(text)

        doc = self._nlp(text)
        relations: List[RelationTuple] = []
        for sentence in doc.sents:
            sent_text = sentence.text.strip()
            if not sent_text:
                continue
            matches = self._regex_extract(sent_text)
            relations.extend(matches)
        return relations


@dataclass(slots=True)
class TextMiningConfig:
    """Configuration for the ``TextMiningPipeline``."""

    grobid_url: str = "http://localhost:8070"
    timeout: int = 60


class TextMiningPipeline:
    """Coordinate PDF fetching, TEI conversion and relation assembly."""

    def __init__(
        self,
        *,
        config: TextMiningConfig | None = None,
        grobid_client: GrobidClient | None = None,
        relation_extractor: RelationExtractor | None = None,
        http_session: "requests.Session" | None = None,
        grounder: GroundingResolver | None = None,
    ) -> None:
        self.config = config or TextMiningConfig()
        self._session = http_session or (requests.Session() if requests is not None else None)
        self._grobid = grobid_client
        if self._grobid is None and requests is not None:
            try:
                self._grobid = GrobidClient(self.config.grobid_url)
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.debug("GROBID client unavailable: %s", exc)
                self._grobid = None
        self._extractor = relation_extractor or SciSpaCyExtractor()
        self._grounder = grounder or GroundingResolver()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def mine(self, record: Mapping[str, object], work_node: Node) -> Tuple[List[Node], List[Edge]]:
        """Return graph fragments derived from ``record``.

        ``record`` is expected to be an OpenAlex work payload.  When the payload
        contains a ``fulltext_tei`` attribute the TEI parsing step is skipped,
        which makes unit tests deterministic and avoids coupling to a live
        GROBID container.
        """

        tei = self._resolve_tei(record)
        if not tei:
            return [], []
        text = _tei_to_plain_text(tei)
        relations = self._extractor.extract(text)
        if not relations:
            return [], []
        nodes, edges = self._assemble_relations(relations, work_node, record)
        return nodes, edges

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_tei(self, record: Mapping[str, object]) -> str:
        tei_inline = record.get("fulltext_tei")
        if isinstance(tei_inline, str) and tei_inline.strip():
            return tei_inline
        pdf_url = self._extract_pdf_url(record)
        if not pdf_url or self._grobid is None or self._session is None:
            return ""
        try:
            response = self._session.get(pdf_url, timeout=self.config.timeout)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network dependent
            LOGGER.debug("Failed to download PDF %s: %s", pdf_url, exc)
            return ""
        try:
            return self._grobid.process_pdf(response.content)
        except Exception as exc:  # pragma: no cover - network dependent
            LOGGER.debug("GROBID processing failed for %s: %s", pdf_url, exc)
            return ""

    def _extract_pdf_url(self, record: Mapping[str, object]) -> str | None:
        locations = []
        best = record.get("best_oa_location")
        if isinstance(best, Mapping):
            locations.append(best)
        primary = record.get("primary_location")
        if isinstance(primary, Mapping):
            locations.append(primary)
        for location in record.get("locations", []) or []:
            if isinstance(location, Mapping):
                locations.append(location)
        for location in locations:
            pdf_url = location.get("pdf_url") or location.get("landing_page_url")
            if pdf_url:
                return str(pdf_url)
        return None

    def _assemble_relations(
        self,
        relations: Sequence[RelationTuple],
        work_node: Node,
        record: Mapping[str, object],
    ) -> Tuple[List[Node], List[Edge]]:
        nodes: Dict[str, Node] = {}
        edges: List[Edge] = []
        publication = record.get("doi") or record.get("id")
        for agent, verb, target, sentence in relations:
            grounded_agent = self._ground(mention=agent)
            grounded_target = self._ground(mention=target)

            subject_id = grounded_agent.id
            object_id = grounded_target.id
            nodes.setdefault(subject_id, self._node_from_grounding(grounded_agent))
            nodes.setdefault(object_id, self._node_from_grounding(grounded_target))

            predicate, relation_label = self._predicate_from_verb(verb)
            base_confidence = 0.6 if predicate == BiolinkPredicate.AFFECTS else 0.5
            confidence = base_confidence * min(grounded_agent.confidence, grounded_target.confidence)
            confidence = float(max(0.2, min(confidence, 0.95)))

            qualifiers = {
                "source_sentence": sentence,
                "work_id": work_node.id,
                "agent_grounding": grounded_agent.provenance,
                "target_grounding": grounded_target.provenance,
            }
            evidence_item = BaseIngestionJob.make_evidence(
                "TextMiningPipeline",
                str(publication) if publication else None,
                confidence,
                sentence=sentence,
                relation=verb,
                agent_id=grounded_agent.id,
                target_id=grounded_target.id,
            )
            evidence_item.annotations["grounding_confidence"] = {
                "agent": grounded_agent.confidence,
                "target": grounded_target.confidence,
            }

            edge = Edge(
                subject=subject_id,
                predicate=predicate,
                object=object_id,
                relation=relation_label,
                confidence=confidence,
                publications=[str(publication)] if publication else [],
                qualifiers=qualifiers,
                evidence=[evidence_item],
            )
            edges.append(edge)
        return list(nodes.values()), edges

    def _predicate_from_verb(self, verb: str) -> Tuple[BiolinkPredicate, str]:
        verb_lower = verb.lower()
        if verb_lower in {"activates", "enhances", "potentiates", "stimulates"}:
            return BiolinkPredicate.AFFECTS, "biolink:positively_regulates"
        if verb_lower in {"inhibits", "suppresses", "attenuates", "represses"}:
            return BiolinkPredicate.AFFECTS, "biolink:negatively_regulates"
        if verb_lower in {"modulates", "alters", "shifts"}:
            return BiolinkPredicate.AFFECTS, "biolink:regulates"
        return BiolinkPredicate.RELATED_TO, "biolink:related_to"

    def _node_from_grounding(self, grounded: GroundedEntity) -> Node:
        attributes: Dict[str, object] = {
            "grounding_confidence": grounded.confidence,
            "grounding_strategy": grounded.provenance.get("strategy") if grounded.provenance else None,
        }
        return Node(
            id=grounded.id,
            name=grounded.name,
            category=grounded.category,
            provided_by="TextMiningPipeline",
            synonyms=list(grounded.synonyms),
            xrefs=list(grounded.xrefs),
            attributes={key: value for key, value in attributes.items() if value is not None},
        )

    def _ground(self, mention: str) -> GroundedEntity:
        try:
            return self._grounder.resolve(mention)
        except Exception:  # pragma: no cover - defensive path
            return GroundedEntity(
                id=f"TXT:{_slugify(mention)}",
                name=mention,
                category=BiolinkEntity.NAMED_THING,
                confidence=0.3,
                synonyms=(mention,),
                provenance={"strategy": "error_fallback"},
            )

__all__ = [
    "GrobidClient",
    "RelationExtractor",
    "SciSpaCyExtractor",
    "TextMiningConfig",
    "TextMiningPipeline",
]

