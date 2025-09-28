from typing import Iterable, List, Sequence, Tuple

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


class _FakeToken:
    def __init__(self, text: str, index: int, *, lemma: str | None = None) -> None:
        self.text = text
        self.lemma_ = lemma or text.lower()
        self.i = index
        self.left_edge = self
        self.right_edge = self
        self.doc = None  # type: ignore[assignment]


class _FakeDoc:
    def __init__(self, text: str, tokens: Sequence[_FakeToken]) -> None:
        self.text = text
        self._tokens = list(tokens)
        for token in self._tokens:
            token.doc = self

    def __getitem__(self, index: int) -> _FakeToken:
        return self._tokens[index]

    def __len__(self) -> int:  # pragma: no cover - not used but mirrors spaCy API
        return len(self._tokens)

    @property
    def sents(self) -> Sequence["_FakeSentence"]:
        return (_FakeSentence(self),)


class _FakeSentence:
    def __init__(self, doc: _FakeDoc) -> None:
        self._doc = doc
        self.text = doc.text

    def as_doc(self) -> _FakeDoc:
        return self._doc


class _FakeMatcher:
    def __init__(self, matches: Iterable[Tuple[int, Tuple[int, int, int]]]) -> None:
        self._matches = list(matches)

    def __call__(self, doc: _FakeDoc) -> List[Tuple[int, Tuple[int, int, int]]]:
        return list(self._matches)


class _FakeNLP:
    def __init__(self, doc: _FakeDoc) -> None:
        self._doc = doc

    def __call__(self, text: str) -> _FakeDoc:
        return self._doc

    def has_pipe(self, name: str) -> bool:  # pragma: no cover - defensive shim
        return True

    def add_pipe(self, name: str, first: bool = False) -> None:  # pragma: no cover - defensive shim
        return None


def test_scispacy_extractor_dependency_matches_multiword_terms() -> None:
    sentence = "5-HT2A receptor activates phospholipase C pathway."
    tokens = [
        _FakeToken("5-HT2A", 0),
        _FakeToken("receptor", 1),
        _FakeToken("activates", 2, lemma="activate"),
        _FakeToken("phospholipase", 3),
        _FakeToken("C", 4),
        _FakeToken("pathway", 5),
        _FakeToken(".", 6),
    ]
    tokens[1].left_edge = tokens[0]
    tokens[1].right_edge = tokens[1]
    tokens[5].left_edge = tokens[3]
    tokens[5].right_edge = tokens[5]
    doc = _FakeDoc(sentence, tokens)
    matcher = _FakeMatcher([(0, (2, 1, 5))])
    extractor = SciSpaCyExtractor(nlp=_FakeNLP(doc), matcher=matcher)

    relations = extractor.extract(sentence)

    assert relations == [("5-HT2A receptor", "activate", "phospholipase C pathway", sentence.strip())]


def test_text_mining_predicate_mapping_handles_lemmatised_verbs() -> None:
    pipeline = TextMiningPipeline(relation_extractor=SciSpaCyExtractor(nlp=None))
    positive = pipeline._predicate_from_verb("activate")
    negative = pipeline._predicate_from_verb("inhibit")
    neutral = pipeline._predicate_from_verb("modulate")

    assert positive == (BiolinkPredicate.AFFECTS, "biolink:positively_regulates")
    assert negative == (BiolinkPredicate.AFFECTS, "biolink:negatively_regulates")
    assert neutral == (BiolinkPredicate.AFFECTS, "biolink:regulates")

