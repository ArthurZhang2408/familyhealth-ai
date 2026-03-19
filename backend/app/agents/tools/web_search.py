"""Web search tool — searches medical sources and academic literature."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.types import ToolDefinition
from app.services.web_search import (
    DRUG_DOMAINS,
    MEDICAL_DOMAINS,
    DuckDuckGoSearchProvider,
    LangSearchProvider,
    PubMedSearchProvider,
    SearchResult,
    SerperSearchProvider,
    TavilySearchProvider,
)

logger = logging.getLogger(__name__)


def build_web_search_tool(
    tavily_api_key: str = "",
    serper_api_keys: list[str] | None = None,
    langsearch_api_keys: list[str] | None = None,
) -> ToolDefinition:
    """Create a ToolDefinition that searches the web for medical information.

    Fallback chain for general/drug searches:
      1. LangSearch + DDG concurrent (merge + dedup by URL)
      2. Tavily (1,000/mo, native domain filtering)
      3. Serper (7,500 total, non-renewable — last resort)
    """

    ddg = DuckDuckGoSearchProvider()

    langsearch: LangSearchProvider | None = None
    if langsearch_api_keys:
        langsearch = LangSearchProvider(langsearch_api_keys)

    serper: SerperSearchProvider | None = None
    if serper_api_keys:
        serper = SerperSearchProvider(serper_api_keys)

    tavily: TavilySearchProvider | None = None
    if tavily_api_key:
        tavily = TavilySearchProvider(tavily_api_key)

    pubmed = PubMedSearchProvider()

    async def _search_with_fallback(
        query: str,
        max_results: int,
        domains: list[str],
    ) -> list[SearchResult]:
        """Try providers, falling through on rate limits or empty results.

        1. LangSearch + DDG fire concurrently, results merged (dedup by URL)
        2. Tavily (1,000/mo, native domain filtering)
        3. Serper (7,500 total non-renewable — last resort)
        """
        # 1. LangSearch + DDG concurrently, aggregate and dedup by URL
        ddg_coro = ddg.search(query, max_results=max_results, allowed_domains=domains)
        if langsearch and langsearch.available:
            ls_coro = langsearch.search(query, max_results=max_results)
            ddg_results, ls_results = await asyncio.gather(ddg_coro, ls_coro)
        else:
            ddg_results = await ddg_coro
            ls_results = []

        # Dedup by URL. LangSearch first (richer AI summaries), DDG fills gaps
        # (domain-filtered medical sources). Both contribute unique URLs.
        seen_urls: set[str] = set()
        merged: list[SearchResult] = []
        for r in ls_results + ddg_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                merged.append(r)

        if merged:
            logger.info(
                "Search merged: %d LangSearch + %d DDG → %d unique",
                len(ls_results), len(ddg_results), len(merged),
            )
            return merged[:max_results]

        logger.info("DDG + LangSearch both returned 0 results, trying Tavily")

        # 2. Tavily (1,000/mo — good quality, native domain filtering)
        if tavily:
            results = await tavily.search(
                query, max_results=max_results, allowed_domains=domains
            )
            if results:
                logger.info("Tavily returned %d results", len(results))
                return results
            logger.info("Tavily returned 0 results, trying Serper")

        # 3. Serper (7,500 total non-renewable — last resort)
        if serper and serper.available:
            results = await serper.search(
                query, max_results=max_results, allowed_domains=domains
            )
            if results:
                logger.info("Serper returned %d results", len(results))
                return results
            logger.info("Serper returned 0 results")

        return []

    async def _handler(
        query: str,
        search_type: str = "general",
        max_results: int = 5,
        **_kwargs: Any,
    ) -> dict:
        max_results = min(max_results, 10)
        if search_type == "academic":
            results = await pubmed.search(query, max_results=max_results)
        elif search_type in ("general", "drug"):
            domains = DRUG_DOMAINS if search_type == "drug" else MEDICAL_DOMAINS
            results = await _search_with_fallback(query, max_results, domains)
        else:
            return {
                "results": [],
                "count": 0,
                "error": (
                    f"Unknown search_type: {search_type}. " "Use 'general', 'academic', or 'drug'."
                ),
            }

        return {
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source": r.source,
                }
                for r in results
            ],
            "count": len(results),
        }

    return ToolDefinition(
        name="web_search",
        description=(
            "Search the web for reliable medical information. Returns results "
            "from curated health sources. Use this to find evidence for your "
            "recommendations, verify drug information, or cite clinical guidelines.\n\n"
            "search_type options:\n"
            '- "general": Search trusted medical websites (Mayo Clinic, CDC, NIH, etc.)\n'
            '- "academic": Search PubMed for peer-reviewed medical literature\n'
            '- "drug": Search drug-specific sources (FDA, Drugs.com, RxList)\n\n'
            "IMPORTANT: Use short keyword queries (3-5 words) for best results. "
            "Do NOT use long natural-language sentences. "
            "If a search returns 0 results, try a different query angle or proceed without."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Short keyword query (3-5 words). Examples: "
                        "'metformin side effects', 'peptic ulcer treatment', "
                        "'tension headache guidelines'. Do NOT use long sentences."
                    ),
                },
                "search_type": {
                    "type": "string",
                    "enum": ["general", "academic", "drug"],
                    "description": (
                        "Type of search: 'general' for medical websites, "
                        "'academic' for PubMed research papers, "
                        "'drug' for medication-specific sources"
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 5, max 10)",
                },
            },
            "required": ["query"],
        },
        handler=_handler,
    )
