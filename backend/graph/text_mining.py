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

from dataclasses import dataclass, field
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



@dataclass(frozen=True)
class ExtractedRelation:
    """Representation of an extracted and grounded relation."""

    agent: GroundedEntity
    target: GroundedEntity
    verb: str
    sentence: str
    method: str
    agent_mention: str
    target_mention: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AssemblyFrame:
    """INDRA/BEL-inspired causal frame created during assembly."""

    frame_id: str
    namespace: str
    relation_type: str
    polarity: str
    agent: GroundedEntity
    target: GroundedEntity
    evidence_text: str
    annotations: Mapping[str, object] = field(default_factory=dict)


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

    def extract(self, text: str) -> List[ExtractedRelation]:  # pragma: no cover - interface
        raise NotImplementedError


class SciSpaCyExtractor(RelationExtractor):
    """scispaCy-backed relation extractor with dependency and linking support."""

    _PATTERN = re.compile(
        r"(?P<agent>[A-Z][A-Za-z0-9-]{2,})\s+(?P<verb>activates|inhibits|modulates|suppresses|enhances)\s+(?P<target>[A-Z][A-Za-z0-9-]{2,})",
        flags=re.IGNORECASE,
    )

    _VERB_NORMALISATIONS = {
        "activates": "activate",
        "enhances": "enhance",
        "suppresses": "suppress",
    }

    def __init__(
        self,
        *,
        nlp=None,
        matcher=None,
        linker=None,
        grounder: GroundingResolver | None = None,
        auto_load: bool = True,
    ) -> None:  # type: ignore[no-untyped-def]
        self._auto_load = auto_load
        self._nlp = nlp
        self._matcher = matcher
        self._linker = linker
        self._grounder = grounder or GroundingResolver()
        if self._nlp is None and self._auto_load:
            try:  # pragma: no cover - optional dependency
                import spacy
                from scispacy.abbreviation import AbbreviationDetector

                self._nlp = spacy.load("en_core_sci_sm")  # type: ignore[assignment]
                if hasattr(self._nlp, "has_pipe") and not self._nlp.has_pipe("sentencizer"):
                    self._nlp.add_pipe("sentencizer", first=True)
                if hasattr(self._nlp, "add_pipe"):
                    try:
                        self._nlp.add_pipe(AbbreviationDetector(self._nlp))
                    except Exception:
                        LOGGER.debug("Failed to add scispaCy abbreviation detector", exc_info=True)
            except Exception:  # pragma: no cover - optional dependency
                self._nlp = None  # type: ignore[assignment]

        if self._nlp is not None and self._matcher is None:
            try:  # pragma: no cover - optional dependency
                from spacy.matcher import DependencyMatcher

                self._matcher = DependencyMatcher(self._nlp.vocab)  # type: ignore[arg-type]
                pattern = [
                    {"RIGHT_ID": "verb", "RIGHT_ATTRS": {"POS": {"IN": ["VERB", "AUX"]}}},
                    {"LEFT_ID": "verb", "REL_OP": ">", "RIGHT_ID": "subject", "RIGHT_ATTRS": {"DEP": {"IN": ["nsubj", "nsubjpass"]}}},
                    {
                        "LEFT_ID": "verb",
                        "REL_OP": ">",
                        "RIGHT_ID": "object",
                        "RIGHT_ATTRS": {"DEP": {"IN": ["dobj", "pobj", "attr", "obl", "dative"]}},
                    },
                ]
                self._matcher.add("AGENT_VERB_TARGET", [pattern])
            except Exception:  # pragma: no cover - optional dependency
                LOGGER.debug("DependencyMatcher unavailable; falling back to regex extraction", exc_info=True)
                self._matcher = None

        if self._nlp is not None and self._linker is None and self._auto_load:
            try:  # pragma: no cover - optional dependency
                if hasattr(self._nlp, "has_pipe") and self._nlp.has_pipe("scispacy_linker"):
                    self._linker = self._nlp.get_pipe("scispacy_linker")
                else:
                    self._nlp.add_pipe("scispacy_linker", config={"resolve_abbreviations": True})
                    self._linker = self._nlp.get_pipe("scispacy_linker")
            except Exception:  # pragma: no cover - optional dependency
                LOGGER.debug("Entity linker unavailable; continuing without KB provenance", exc_info=True)
                self._linker = None

    def _regex_extract(self, text: str) -> List[ExtractedRelation]:
        relations: List[ExtractedRelation] = []
        for match in self._PATTERN.finditer(text):
            agent = match.group("agent")
            verb = match.group("verb").lower()
            verb_norm = self._VERB_NORMALISATIONS.get(verb, verb)
            target = match.group("target")
            sentence = match.group(0).strip()
            grounded_agent = self._ground(agent, method="regex_fallback")
            grounded_target = self._ground(target, method="regex_fallback")
            relations.append(
                ExtractedRelation(
                    agent=grounded_agent,
                    target=grounded_target,
                    verb=verb_norm,
                    sentence=sentence,
                    method="regex_fallback",
                    agent_mention=agent,
                    target_mention=target,
                    metadata={"pattern": "simple_verb_pattern"},
                )
            )
        return relations

    def _expand_phrase(self, token):  # type: ignore[no-untyped-def]
        doc = getattr(token, "doc", None)
        left = getattr(token, "left_edge", token)
        right = getattr(token, "right_edge", token)
        start = getattr(left, "i", getattr(token, "i", 0))
        end = getattr(right, "i", getattr(token, "i", start))
        words: List[str] = []
        if doc is not None:
            for index in range(start, end + 1):
                try:
                    words.append(doc[index].text)
                except Exception:  # pragma: no cover - defensive
                    break
        phrase = " ".join(words).strip()
        return phrase or token.text, start, end, doc

    def _link_span(self, span) -> Tuple[str | None, Dict[str, object]]:  # type: ignore[no-untyped-def]
        canonical: str | None = None
        metadata: Dict[str, object] = {}
        if span is None:
            return canonical, metadata
        extension = getattr(span, "_", None)
        candidates: Iterable[Tuple[str, float]] | None = None
        if extension is not None and hasattr(extension, "kb_ents"):
            try:
                kb_entries = list(extension.kb_ents)
            except Exception:  # pragma: no cover - defensive
                kb_entries = []
            if kb_entries:
                limited = kb_entries[:5]
                metadata["kb_ents"] = [(str(kb_id), float(score)) for kb_id, score in limited]
                candidates = limited
        if candidates and self._linker is not None:
            try:
                best_id = candidates[0][0]
                entity = self._linker.kb.cui_to_entity.get(best_id)
                if entity is not None:
                    canonical = entity.canonical_name
                    metadata["canonical_name"] = canonical
                    metadata["linker_name"] = getattr(self._linker, "name", "scispacy_linker")
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Failed to resolve linker candidate", exc_info=True)
        return canonical, metadata

    def _ground(
        self,
        mention: str,
        *,
        method: str,
        surface: str | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> GroundedEntity:
        surface_mention = surface or mention
        metadata: Dict[str, object] = {
            "surface_mention": surface_mention,
            "normalised_mention": mention,
            "extraction_method": method,
        }
        if extra:
            metadata.update(dict(extra))
        try:
            resolved = self._grounder.resolve(mention)
        except Exception:  # pragma: no cover - defensive fallback
            return GroundedEntity(
                id=f"TXT:{_slugify(surface_mention)}",
                name=surface_mention,
                category=BiolinkEntity.NAMED_THING,
                confidence=0.3,
                synonyms=(surface_mention,),
                provenance={**metadata, "strategy": "extractor_fallback"},
            )

        provenance = dict(resolved.provenance or {})
        provenance.update(metadata)
        synonyms = tuple(resolved.synonyms)
        if surface_mention and surface_mention not in synonyms:
            synonyms = synonyms + (surface_mention,)
        return GroundedEntity(
            id=resolved.id,
            name=resolved.name,
            category=resolved.category,
            confidence=resolved.confidence,
            synonyms=synonyms,
            xrefs=resolved.xrefs,
            provenance=provenance,
        )

    def _make_span(self, doc, start: int, end: int):  # type: ignore[no-untyped-def]
        if doc is None:
            return None
        try:
            return doc[start : end + 1]
        except Exception:  # pragma: no cover - defensive
            return None

    def _scispacy_extract(self, doc) -> List[ExtractedRelation]:  # type: ignore[no-untyped-def]
        if self._matcher is None:
            return []
        relations: List[ExtractedRelation] = []
        seen: set[Tuple[str, str, str, str]] = set()
        for sentence in getattr(doc, "sents", []):
            sent_text = sentence.text.strip()
            if not sent_text:
                continue
            try:
                sent_doc = sentence.as_doc()
            except Exception:  # pragma: no cover - defensive
                sent_doc = doc
            try:
                matches = self._matcher(sent_doc)
            except Exception:  # pragma: no cover - defensive
                matches = []
            for _, token_ids in matches:
                if len(token_ids) < 3:
                    continue
                verb = sent_doc[token_ids[0]]
                subject = sent_doc[token_ids[1]]
                obj = sent_doc[token_ids[2]]
                agent_text, agent_start, agent_end, agent_doc = self._expand_phrase(subject)
                target_text, target_start, target_end, target_doc = self._expand_phrase(obj)
                agent_span = self._make_span(agent_doc, agent_start, agent_end)
                target_span = self._make_span(target_doc, target_start, target_end)
                canonical_agent, agent_meta = self._link_span(agent_span)
                canonical_target, target_meta = self._link_span(target_span)
                verb_text = (verb.lemma_ or verb.text).lower()
                verb_text = self._VERB_NORMALISATIONS.get(verb_text, verb_text)
                key = (agent_text, verb_text, target_text, sent_text)
                if key in seen:
                    continue
                seen.add(key)
                agent_grounded = self._ground(
                    canonical_agent or agent_text,
                    method="dependency_matcher",
                    surface=agent_text,
                    extra={"linking": agent_meta} if agent_meta else agent_meta,
                )
                target_grounded = self._ground(
                    canonical_target or target_text,
                    method="dependency_matcher",
                    surface=target_text,
                    extra={"linking": target_meta} if target_meta else target_meta,
                )
                metadata = {
                    "pattern": "dependency_matcher",
                    "agent_indices": (agent_start, agent_end),
                    "target_indices": (target_start, target_end),
                }
                if agent_meta:
                    metadata["agent_linking"] = agent_meta
                if target_meta:
                    metadata["target_linking"] = target_meta
                relations.append(
                    ExtractedRelation(
                        agent=agent_grounded,
                        target=target_grounded,
                        verb=verb_text,
                        sentence=sent_text,
                        method="dependency_matcher",
                        agent_mention=agent_text,
                        target_mention=target_text,
                        metadata=metadata,
                    )
                )
        return relations

    def extract(self, text: str) -> List[ExtractedRelation]:
        if not text:
            return []
        if self._nlp is None:
            return self._regex_extract(text)

        doc = self._nlp(text)
        relations = self._scispacy_extract(doc)
        if relations:
            return relations
        for sentence in getattr(doc, "sents", []):
            sent_text = sentence.text.strip()
            if not sent_text:
                continue
            relations.extend(self._regex_extract(sent_text))
        if not relations:
            relations = self._regex_extract(text)
        return relations


@dataclass(slots=True)
class TextMiningConfig:
    """Configuration for the ``TextMiningPipeline``."""

    grobid_url: str = "http://localhost:8070"
    timeout: int = 60
    prefer_scispacy: bool = True


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
        self._grounder = grounder or GroundingResolver()
        if relation_extractor is None:
            self._extractor = SciSpaCyExtractor(
                grounder=self._grounder,
                auto_load=self.config.prefer_scispacy,
            )
        else:
            self._extractor = relation_extractor

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
        relations = self._normalise_relations(self._extractor.extract(text))
        if not relations:
            return [], []
        nodes, edges = self._assemble_relations(relations, work_node, record)
        return nodes, edges

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _normalise_relations(self, relations: Sequence[object]) -> List[ExtractedRelation]:
        normalised: List[ExtractedRelation] = []
        for relation in relations:
            if isinstance(relation, ExtractedRelation):
                normalised.append(relation)
                continue
            if isinstance(relation, tuple) and len(relation) == 4:
                agent, verb, target, sentence = relation
                agent_text = str(agent)
                target_text = str(target)
                verb_text = str(verb)
                sentence_text = str(sentence).strip()
                grounded_agent = self._ground(agent_text)
                grounded_target = self._ground(target_text)
                normalised.append(
                    ExtractedRelation(
                        agent=grounded_agent,
                        target=grounded_target,
                        verb=verb_text,
                        sentence=sentence_text,
                        method="legacy_fallback",
                        agent_mention=agent_text,
                        target_mention=target_text,
                        metadata={"source": "legacy_tuple"},
                    )
                )
        return normalised

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
        relations: Sequence[ExtractedRelation],
        work_node: Node,
        record: Mapping[str, object],
    ) -> Tuple[List[Node], List[Edge]]:
        nodes: Dict[str, Node] = {}
        edges: List[Edge] = []
        publication = record.get("doi") or record.get("id")
        assemblies = self._build_assembly_frames(relations, work_node)

        for relation, frame, predicate, relation_label in assemblies:
            grounded_agent = relation.agent
            grounded_target = relation.target

            subject_id = grounded_agent.id
            object_id = grounded_target.id
            nodes.setdefault(subject_id, self._node_from_grounding(grounded_agent))
            nodes.setdefault(object_id, self._node_from_grounding(grounded_target))

            base_confidence = 0.6 if predicate == BiolinkPredicate.AFFECTS else 0.5
            confidence = base_confidence * min(grounded_agent.confidence, grounded_target.confidence)
            confidence = float(max(0.2, min(confidence, 0.95)))

            qualifiers = {
                "source_sentence": relation.sentence,
                "work_id": work_node.id,
                "agent_grounding": grounded_agent.provenance,
                "target_grounding": grounded_target.provenance,
                "assembly_frame_id": frame.frame_id,
                "assembly_relation_type": frame.relation_type,
                "assembly_polarity": frame.polarity,
                "extraction_method": relation.method,
                "extraction_metadata": dict(relation.metadata),
            }
            evidence_item = BaseIngestionJob.make_evidence(
                "TextMiningPipeline",
                str(publication) if publication else None,
                confidence,
                sentence=relation.sentence,
                relation=relation.verb,
                agent_id=grounded_agent.id,
                target_id=grounded_target.id,
                assembly_frame=frame.frame_id,
            )
            evidence_item.annotations["grounding_confidence"] = {
                "agent": grounded_agent.confidence,
                "target": grounded_target.confidence,
            }
            evidence_item.annotations["assembly_relation_type"] = frame.relation_type
            evidence_item.annotations["assembly_namespace"] = frame.namespace

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

    def _build_assembly_frames(
        self,
        relations: Sequence[ExtractedRelation],
        work_node: Node,
    ) -> List[Tuple[ExtractedRelation, AssemblyFrame, BiolinkPredicate, str]]:
        assemblies: List[Tuple[ExtractedRelation, AssemblyFrame, BiolinkPredicate, str]] = []
        for index, relation in enumerate(relations, start=1):
            predicate, relation_label = self._predicate_from_verb(relation.verb)
            relation_type, polarity = self._relation_type_from_label(relation_label)
            frame_id = f"FRAME:{_slugify(work_node.id)}:{index}"
            annotations = {
                "verb": relation.verb,
                "work_id": work_node.id,
                "extraction_method": relation.method,
            }
            frame = AssemblyFrame(
                frame_id=frame_id,
                namespace="INDRA-lite",
                relation_type=relation_type,
                polarity=polarity,
                agent=relation.agent,
                target=relation.target,
                evidence_text=relation.sentence,
                annotations=annotations,
            )
            assemblies.append((relation, frame, predicate, relation_label))
        return assemblies

    def _predicate_from_verb(self, verb: str) -> Tuple[BiolinkPredicate, str]:
        verb_lower = verb.lower()
        positive = {"activate", "activates", "enhance", "enhances", "potentiate", "potentiates", "stimulate", "stimulates"}
        negative = {"inhibit", "inhibits", "suppress", "suppresses", "attenuate", "attenuates", "repress", "represses"}
        neutral = {"modulate", "modulates", "alter", "alters", "shift", "shifts"}
        if verb_lower in positive:
            return BiolinkPredicate.AFFECTS, "biolink:positively_regulates"
        if verb_lower in negative:
            return BiolinkPredicate.AFFECTS, "biolink:negatively_regulates"
        if verb_lower in neutral:
            return BiolinkPredicate.AFFECTS, "biolink:regulates"
        return BiolinkPredicate.RELATED_TO, "biolink:related_to"

    @staticmethod
    def _relation_type_from_label(relation_label: str) -> Tuple[str, str]:
        if relation_label.endswith("positively_regulates"):
            return "Activation", "positive"
        if relation_label.endswith("negatively_regulates"):
            return "Inhibition", "negative"
        if relation_label.endswith("regulates"):
            return "Regulation", "neutral"
        return "Association", "unknown"

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
    "ExtractedRelation",
    "AssemblyFrame",
]

