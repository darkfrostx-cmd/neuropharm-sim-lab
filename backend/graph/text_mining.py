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
            subject_id = f"TXT:{_slugify(agent)}"
            object_id = f"TXT:{_slugify(target)}"
            nodes.setdefault(
                subject_id,
                Node(
                    id=subject_id,
                    name=agent,
                    category=BiolinkEntity.NAMED_THING,
                    provided_by="TextMiningPipeline",
                ),
            )
            nodes.setdefault(
                object_id,
                Node(
                    id=object_id,
                    name=target,
                    category=BiolinkEntity.NAMED_THING,
                    provided_by="TextMiningPipeline",
                ),
            )
            predicate = self._predicate_from_verb(verb)
            evidence_item = BaseIngestionJob.make_evidence(
                "TextMiningPipeline",
                str(publication) if publication else None,
                0.55,
                sentence=sentence,
                relation=verb,
            )
            edge = Edge(
                subject=subject_id,
                predicate=predicate,
                object=object_id,
                confidence=0.55 if predicate == BiolinkPredicate.AFFECTS else 0.45,
                publications=[str(publication)] if publication else [],
                qualifiers={
                    "source_sentence": sentence,
                    "work_id": work_node.id,
                },
                evidence=[evidence_item],
            )
            edges.append(edge)
        return list(nodes.values()), edges

    def _predicate_from_verb(self, verb: str) -> BiolinkPredicate:
        verb_lower = verb.lower()
        if verb_lower in {"activates", "enhances", "potentiates"}:
            return BiolinkPredicate.AFFECTS
        if verb_lower in {"inhibits", "suppresses", "attenuates"}:
            return BiolinkPredicate.AFFECTS
        return BiolinkPredicate.RELATED_TO

__all__ = [
    "GrobidClient",
    "RelationExtractor",
    "SciSpaCyExtractor",
    "TextMiningConfig",
    "TextMiningPipeline",
]

