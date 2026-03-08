"""Web search providers — DuckDuckGo, Tavily (fallback), and PubMed (academic)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape

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
# Shared result type
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Normalized search result from any provider."""

    title: str
    url: str
    snippet: str
    source: str  # domain name or "PubMed"
    published_date: str | None = None


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
# DuckDuckGo (free, no API key — primary for general/drug search)
# ---------------------------------------------------------------------------

DDG_URL = "https://html.duckduckgo.com/html/"
DDG_TIMEOUT = 10.0

# Regex to extract result links and snippets from DDG HTML
_DDG_RESULT_RE = re.compile(
    r'class="result__a"\s+href="(?P<url>[^"]+)"[^>]*>'
    r"(?P<title>.*?)</a>.*?"
    r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)


def _clean_html(text: str) -> str:
    """Strip HTML tags and unescape entities."""
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _extract_domain(url: str) -> str:
    return url.split("//")[-1].split("/")[0].removeprefix("www.")


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
            logger.warning("DuckDuckGo search timed out for query: %s", query)
            return []
        except Exception:
            logger.exception("DuckDuckGo search failed for query: %s", query)
            return []

        results: list[SearchResult] = []
        for match in _DDG_RESULT_RE.finditer(html):
            url = unescape(match.group("url"))
            # DDG wraps URLs in a redirect — extract the actual URL
            if "uddg=" in url:
                from urllib.parse import parse_qs, urlparse

                parsed = parse_qs(urlparse(url).query)
                url = parsed.get("uddg", [url])[0]

            domain = _extract_domain(url)

            # Filter to allowed domains if specified
            if allowed_domains:
                if not any(d in domain for d in allowed_domains):
                    continue

            results.append(
                SearchResult(
                    title=_clean_html(match.group("title")),
                    url=url,
                    snippet=_clean_html(match.group("snippet"))[:500],
                    source=domain,
                )
            )
            if len(results) >= max_results:
                break

        return results


# ---------------------------------------------------------------------------
# Tavily (fallback for general/drug search when DDG fails)
# ---------------------------------------------------------------------------

TAVILY_URL = "https://api.tavily.com/search"
TAVILY_TIMEOUT = 10.0


class TavilySearchProvider:
    """Wraps the Tavily REST API for general web search with domain filtering."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        include_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
        }
        if include_domains:
            payload["include_domains"] = include_domains

        try:
            async with httpx.AsyncClient(timeout=TAVILY_TIMEOUT) as client:
                resp = await client.post(TAVILY_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning("Tavily search timed out for query: %s", query)
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("Tavily search HTTP %d for query: %s", exc.response.status_code, query)
            return []
        except Exception:
            logger.exception("Tavily search failed for query: %s", query)
            return []

        results: list[SearchResult] = []
        for item in data.get("results", []):
            url = item.get("url", "")
            # Extract domain for source label
            source = url.split("//")[-1].split("/")[0] if url else "unknown"
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("content", "")[:500],
                    source=source,
                    published_date=item.get("published_date"),
                )
            )
        return results


# ---------------------------------------------------------------------------
# PubMed E-utilities
# ---------------------------------------------------------------------------

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_TIMEOUT = 10.0


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
            # PubMed treats words as AND — long queries often return 0.
            # Retry with only medical keywords (drop filler words).
            keywords = _extract_medical_keywords(query)
            if keywords != query.lower().strip():
                logger.info("PubMed retry with keywords: %s", keywords)
                results = await self._esearch(keywords, max_results=max_results)
        return results

    async def _esearch(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
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
            async with httpx.AsyncClient(timeout=PUBMED_TIMEOUT) as client:
                search_resp = await client.get(
                    f"{PUBMED_BASE}/esearch.fcgi", params=search_params
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()

                id_list = search_data.get("esearchresult", {}).get("idlist", [])
                if not id_list:
                    return []

                # Step 2: esummary — get metadata for PMIDs
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
            logger.warning("PubMed search timed out for query: %s", query)
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "PubMed search HTTP %d for query: %s",
                exc.response.status_code,
                query,
            )
            return []
        except Exception:
            logger.exception("PubMed search failed for query: %s", query)
            return []

        results: list[SearchResult] = []
        result_map = summary_data.get("result", {})
        for pmid in id_list:
            article = result_map.get(pmid)
            if not article or not isinstance(article, dict):
                continue

            # Build author string
            authors = article.get("authors", [])
            author_str = ""
            if authors:
                first = authors[0].get("name", "")
                author_str = f"{first} et al." if len(authors) > 1 else first

            # Build snippet from title + source journal + authors
            journal = article.get("fulljournalname", article.get("source", ""))
            pub_date = article.get("pubdate", "")
            snippet_parts = []
            if author_str:
                snippet_parts.append(author_str)
            if journal:
                snippet_parts.append(journal)
            if pub_date:
                snippet_parts.append(pub_date)

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
