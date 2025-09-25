"""Unified literature retrieval helpers for gap analysis and reasoning."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from typing import Dict, Iterable, List, Optional, Protocol, Sequence

try:  # pragma: no cover - optional dependency for live fetches
    import requests
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]

from .ingest_openalex import OpenAlexClient


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LiteratureRecord:
    """Normalized representation of a literature search hit."""

    title: str
    identifier: str | None
    year: int | None
    source: str
    score: float
    url: str | None = None
    snippet: str | None = None

    def merge(self, other: "LiteratureRecord") -> "LiteratureRecord":
        """Return a best-effort merge of two records describing the same work."""

        score = max(self.score, other.score)
        year = self.year or other.year
        snippet = self.snippet or other.snippet
        url = self.url or other.url
        title = self.title if len(self.title) >= len(other.title) else other.title
        identifier = self.identifier or other.identifier
        return replace(self, title=title, identifier=identifier, year=year, score=score, url=url, snippet=snippet)


class LiteratureClient(Protocol):
    """Protocol implemented by provider specific search clients."""

    def search(self, query: str, *, limit: int = 5) -> Iterable[LiteratureRecord]:
        ...  # pragma: no cover - protocol


class OpenAlexSearch(LiteratureClient):
    """Adapter exposing ``OpenAlexClient`` via the unified protocol."""

    def __init__(self, client: OpenAlexClient | None = None) -> None:
        self._client = client or OpenAlexClient()

    def search(self, query: str, *, limit: int = 5) -> Iterable[LiteratureRecord]:
        count = 0
        for record in self._client.iter_works(search=query, per_page=max(25, limit)):
            title = record.get("display_name") or "Unknown work"
            identifier: Optional[str] = record.get("id")
            if not identifier:
                ids = record.get("ids", {})
                if isinstance(ids, dict):
                    identifier = ids.get("openalex") or ids.get("doi")
            score = float(record.get("cited_by_count") or 0.0)
            snippet = None
            abstract_inverted = record.get("abstract_inverted_index")
            if isinstance(abstract_inverted, dict):
                # reconstruct short snippet similar to OpenAlex docs
                words: Dict[int, str] = {}
                for word, positions in abstract_inverted.items():
                    for pos in positions or []:
                        words[int(pos)] = word
                if words:
                    snippet = " ".join(words[index] for index in sorted(words)[:40])
            year = record.get("publication_year")
            url = None
            best = record.get("best_oa_location")
            if isinstance(best, dict):
                url = best.get("url") or best.get("landing_page_url")
            yield LiteratureRecord(
                title=title,
                identifier=str(identifier) if identifier else None,
                year=int(year) if isinstance(year, int) else None,
                source="OpenAlex",
                score=score,
                url=str(url) if url else None,
                snippet=snippet,
            )
            count += 1
            if count >= limit:
                break


class SemanticScholarClient(LiteratureClient):
    """Client for the public Semantic Scholar search API."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, session: "requests.Session" | None = None) -> None:
        if requests is None:  # pragma: no cover - optional dependency
            raise ImportError("requests is required for SemanticScholarClient")
        self._session = session or requests.Session()

    def search(self, query: str, *, limit: int = 5) -> Iterable[LiteratureRecord]:
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,year,url,abstract,citationCount"
        }
        response = self._session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or []
        for item in data:
            title = item.get("title") or "Unknown work"
            identifier = item.get("paperId")
            year = item.get("year")
            url = item.get("url")
            score = float(item.get("citationCount") or 0.0)
            snippet = item.get("abstract")
            yield LiteratureRecord(
                title=title,
                identifier=str(identifier) if identifier else None,
                year=int(year) if isinstance(year, int) else None,
                source="Semantic Scholar",
                score=score,
                url=str(url) if url else None,
                snippet=snippet,
            )


class LiteratureAggregator:
    """Fan out queries across multiple literature providers and deduplicate hits."""

    def __init__(self, clients: Sequence[LiteratureClient] | None = None) -> None:
        if clients is not None:
            self._clients = list(clients)
        else:
            auto_clients: List[LiteratureClient] = []
            try:
                auto_clients.append(OpenAlexSearch())
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.debug("OpenAlex search unavailable: %s", exc)
            try:
                auto_clients.append(SemanticScholarClient())
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.debug("Semantic Scholar search unavailable: %s", exc)
            self._clients = auto_clients

    def suggest(self, subject: str, target: str, *, limit: int = 5) -> List[LiteratureRecord]:
        if not self._clients:
            return []
        query = f"{subject} {target}".strip()
        aggregated: Dict[str, LiteratureRecord] = {}
        fallback_index = 0
        for client in self._clients:
            try:
                for record in client.search(query, limit=limit):
                    key = (record.identifier or "").lower() or record.title.lower()
                    if key in aggregated:
                        aggregated[key] = aggregated[key].merge(record)
                    else:
                        aggregated[key] = record
                        fallback_index += 1
                        if fallback_index >= limit * 3:
                            break
            except Exception as exc:  # pragma: no cover - network dependent
                LOGGER.debug("Literature client %s failed: %s", client.__class__.__name__, exc)
        records = list(aggregated.values())
        records.sort(key=lambda rec: (rec.score, rec.year or 0), reverse=True)
        return records[:limit]


__all__ = [
    "LiteratureAggregator",
    "LiteratureClient",
    "LiteratureRecord",
    "OpenAlexSearch",
    "SemanticScholarClient",
]

