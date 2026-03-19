"""Web search providers — DuckDuckGo, LangSearch, Serper, Tavily, PubMed."""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html import unescape
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    "a an the and or but in on of to for with after before from by is are was "
    "were be been being have has had do does did will would shall should may "
    "might can could my your their its that this these those it i e.g. etc".split()
)


def _extract_medical_keywords(query: str, max_words: int = 4) -> str:
    """Drop filler words and cap at max_words for PubMed-style search."""
    words = [w for w in query.lower().split() if w not in _STOP_WORDS]
    return " ".join(words[:max_words])


# ---------------------------------------------------------------------------
# Shared result type & helpers
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Normalized search result from any provider."""

    title: str
    url: str
    snippet: str
    source: str  # domain name or "PubMed"
    published_date: str | None = None


def _extract_domain(url: str) -> str:
    return url.split("//")[-1].split("/")[0].removeprefix("www.")


def _clean_html(text: str) -> str:
    """Strip HTML tags and unescape entities."""
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _filter_by_domain(
    results: list[SearchResult],
    allowed_domains: list[str] | None,
    max_results: int,
) -> list[SearchResult]:
    """Filter results to allowed domains and cap at max_results."""
    if not allowed_domains:
        return results[:max_results]
    filtered = [
        r for r in results
        if any(d in r.source for d in allowed_domains)
    ]
    return filtered[:max_results]


# ---------------------------------------------------------------------------
# Domain whitelists
# ---------------------------------------------------------------------------

MEDICAL_DOMAINS = [
    "mayoclinic.org",
    "cdc.gov",
    "who.int",
    "medlineplus.gov",
    "nih.gov",
    "clevelandclinic.org",
    "healthline.com",
    "drugs.com",
]

DRUG_DOMAINS = [
    "drugs.com",
    "rxlist.com",
    "medlineplus.gov",
    "fda.gov",
    "webmd.com",
]


# ---------------------------------------------------------------------------
# Rotating key pool — shared by keyed providers
# ---------------------------------------------------------------------------

_KEY_COOLDOWN_S = 5.0


class _RotatingKeyPool:
    """Round-robin key rotation with per-key cooldowns.

    On 429: the key cools down for a few seconds (QPS/QPM burst).
    On 402: the key is marked permanently dead (quota gone).
    """

    def __init__(self, keys: list[str], name: str = "pool") -> None:
        self._keys = list(keys)
        self._name = name
        self._next = 0
        self._cooldowns: dict[int, float] = {}
        self._dead: set[int] = set()

    @property
    def available(self) -> bool:
        now = time.monotonic()
        return any(
            i not in self._dead and self._cooldowns.get(i, 0) <= now
            for i in range(len(self._keys))
        )

    def get_key(self) -> str | None:
        now = time.monotonic()
        for _ in range(len(self._keys)):
            idx = self._next % len(self._keys)
            self._next += 1
            if idx in self._dead:
                continue
            if self._cooldowns.get(idx, 0) > now:
                continue
            return self._keys[idx]
        return None

    def report_429(self, key: str) -> None:
        try:
            idx = self._keys.index(key)
            self._cooldowns[idx] = time.monotonic() + _KEY_COOLDOWN_S
            logger.info("%s key #%d: 429 cooldown %.0fs", self._name, idx + 1, _KEY_COOLDOWN_S)
        except ValueError:
            pass

    def report_402(self, key: str) -> None:
        try:
            idx = self._keys.index(key)
            self._dead.add(idx)
            alive = len(self._keys) - len(self._dead)
            logger.warning(
                "%s key #%d: permanently exhausted, %d keys remaining",
                self._name, idx + 1, alive,
            )
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Base class for keyed API providers (LangSearch, Serper, etc.)
# ---------------------------------------------------------------------------


class _KeyedSearchProvider(ABC):
    """Base class for search providers that use rotating API keys.

    Subclasses only define request construction and response parsing.
    Retry loop, key rotation, error handling, and domain filtering are shared.
    """

    def __init__(
        self, api_keys: list[str], name: str, url: str, timeout: float, max_count: int = 10
    ) -> None:
        self._pool = _RotatingKeyPool(api_keys, name=name)
        self._name = name
        self._url = url
        self._timeout = timeout
        self._max_count = max_count

    @property
    def available(self) -> bool:
        return self._pool.available

    @abstractmethod
    def _build_request(
        self, key: str, query: str, count: int
    ) -> tuple[dict[str, str], Any]:
        """Return (headers, payload) for the HTTP POST request."""

    @abstractmethod
    def _parse_response(self, data: dict) -> list[SearchResult]:
        """Parse the API JSON response into SearchResult list."""

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        allowed_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        # Over-fetch when domain filtering — more candidates to filter from
        fetch_count = self._max_count if allowed_domains else max_results

        for _attempt in range(3):
            key = self._pool.get_key()
            if key is None:
                logger.warning("All %s keys unavailable", self._name)
                return []

            headers, payload = self._build_request(key, query, fetch_count)
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(self._url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        self._pool.report_429(key)
                        continue
                    if resp.status_code == 402:
                        self._pool.report_402(key)
                        continue
                    resp.raise_for_status()
                    results = self._parse_response(resp.json())
                    return _filter_by_domain(results, allowed_domains, max_results)
            except httpx.TimeoutException:
                logger.warning("%s timed out for query: %s", self._name, query)
                return []
            except Exception:
                logger.exception("%s failed for query: %s", self._name, query)
                return []

        return []


# ---------------------------------------------------------------------------
# DuckDuckGo (free, no API key — HTML scraping)
# ---------------------------------------------------------------------------

DDG_URL = "https://html.duckduckgo.com/html/"
DDG_TIMEOUT = 10.0

_DDG_RESULT_RE = re.compile(
    r'class="result__a"\s+href="(?P<url>[^"]+)"[^>]*>'
    r"(?P<title>.*?)</a>.*?"
    r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)


class DuckDuckGoSearchProvider:
    """Scrapes DuckDuckGo HTML search — free, no API key required."""

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        allowed_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=DDG_TIMEOUT) as client:
                resp = await client.post(
                    DDG_URL,
                    data={"q": query, "b": ""},
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                html = resp.text
        except httpx.TimeoutException:
            logger.warning("DuckDuckGo timed out for query: %s", query)
            return []
        except Exception:
            logger.exception("DuckDuckGo failed for query: %s", query)
            return []

        results: list[SearchResult] = []
        for match in _DDG_RESULT_RE.finditer(html):
            url = unescape(match.group("url"))
            if "uddg=" in url:
                from urllib.parse import parse_qs, urlparse

                parsed = parse_qs(urlparse(url).query)
                url = parsed.get("uddg", [url])[0]

            domain = _extract_domain(url)
            results.append(
                SearchResult(
                    title=_clean_html(match.group("title")),
                    url=url,
                    snippet=_clean_html(match.group("snippet"))[:500],
                    source=domain,
                )
            )

        return _filter_by_domain(results, allowed_domains, max_results)


# ---------------------------------------------------------------------------
# LangSearch (free tier: 1,000 queries/day per account)
# ---------------------------------------------------------------------------


class LangSearchProvider(_KeyedSearchProvider):
    """LangSearch Web Search API — AI-optimized with rich summaries."""

    def __init__(self, api_keys: list[str]) -> None:
        super().__init__(
            api_keys, name="LangSearch",
            url="https://api.langsearch.com/v1/web-search", timeout=10.0,
        )

    def _build_request(self, key, query, count):
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "freshness": "noLimit",
            "summary": True,
            "count": min(count, 10),
        }
        return headers, payload

    def _parse_response(self, data):
        results = []
        for item in data.get("data", {}).get("webPages", {}).get("value", []):
            url = item.get("url", "")
            snippet = item.get("summary") or item.get("snippet") or ""
            results.append(
                SearchResult(
                    title=item.get("name", ""),
                    url=url,
                    snippet=snippet[:500],
                    source=_extract_domain(url),
                    published_date=item.get("datePublished"),
                )
            )
        return results


# ---------------------------------------------------------------------------
# Serper (Google results, free tier: 2,500 queries per key)
# ---------------------------------------------------------------------------


class SerperSearchProvider(_KeyedSearchProvider):
    """Serper.dev — Google search results via API."""

    def __init__(self, api_keys: list[str]) -> None:
        super().__init__(
            api_keys, name="Serper",
            url="https://google.serper.dev/search", timeout=10.0,
        )

    def _build_request(self, key, query, count):
        headers = {"X-API-KEY": key, "Content-Type": "application/json"}
        payload = {"q": query, "num": count}
        return headers, payload

    def _parse_response(self, data):
        results = []
        for item in data.get("organic", []):
            url = item.get("link", "")
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("snippet", "")[:500],
                    source=_extract_domain(url),
                )
            )
        return results


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------


class TavilySearchProvider:
    """Wraps the Tavily REST API — supports native domain filtering."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        allowed_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        payload: dict = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
        }
        if allowed_domains:
            payload["include_domains"] = allowed_domains

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://api.tavily.com/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning("Tavily timed out for query: %s", query)
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("Tavily HTTP %d for query: %s", exc.response.status_code, query)
            return []
        except Exception:
            logger.exception("Tavily failed for query: %s", query)
            return []

        results: list[SearchResult] = []
        for item in data.get("results", []):
            url = item.get("url", "")
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("content", "")[:500],
                    source=_extract_domain(url) if url else "unknown",
                    published_date=item.get("published_date"),
                )
            )
        return results


# ---------------------------------------------------------------------------
# PubMed E-utilities
# ---------------------------------------------------------------------------

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedSearchProvider:
    """Wraps NCBI E-utilities for PubMed academic literature search."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        results = await self._esearch(query, max_results=max_results)
        if not results:
            keywords = _extract_medical_keywords(query)
            if keywords != query.lower().strip():
                logger.info("PubMed retry with keywords: %s", keywords)
                results = await self._esearch(keywords, max_results=max_results)
        return results

    async def _esearch(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        search_params: dict = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results,
            "sort": "relevance",
        }
        if self._api_key:
            search_params["api_key"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                search_resp = await client.get(
                    f"{PUBMED_BASE}/esearch.fcgi", params=search_params
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()

                id_list = search_data.get("esearchresult", {}).get("idlist", [])
                if not id_list:
                    return []

                summary_params: dict = {
                    "db": "pubmed",
                    "id": ",".join(id_list),
                    "retmode": "json",
                }
                if self._api_key:
                    summary_params["api_key"] = self._api_key

                summary_resp = await client.get(
                    f"{PUBMED_BASE}/esummary.fcgi", params=summary_params
                )
                summary_resp.raise_for_status()
                summary_data = summary_resp.json()
        except httpx.TimeoutException:
            logger.warning("PubMed timed out for query: %s", query)
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("PubMed HTTP %d for query: %s", exc.response.status_code, query)
            return []
        except Exception:
            logger.exception("PubMed failed for query: %s", query)
            return []

        results: list[SearchResult] = []
        result_map = summary_data.get("result", {})
        for pmid in id_list:
            article = result_map.get(pmid)
            if not article or not isinstance(article, dict):
                continue

            authors = article.get("authors", [])
            author_str = ""
            if authors:
                first = authors[0].get("name", "")
                author_str = f"{first} et al." if len(authors) > 1 else first

            journal = article.get("fulljournalname", article.get("source", ""))
            pub_date = article.get("pubdate", "")
            snippet_parts = [p for p in (author_str, journal, pub_date) if p]

            results.append(
                SearchResult(
                    title=article.get("title", ""),
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    snippet=". ".join(snippet_parts),
                    source="PubMed",
                    published_date=pub_date or None,
                )
            )
        return results
