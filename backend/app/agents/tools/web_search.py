"""Web search tool — searches medical sources and academic literature."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.types import ToolDefinition
from app.services.web_search import (
    DRUG_DOMAINS,
    MEDICAL_DOMAINS,
    DuckDuckGoSearchProvider,
    PubMedSearchProvider,
    TavilySearchProvider,
)

logger = logging.getLogger(__name__)


def build_web_search_tool(
    tavily_api_key: str = "",
) -> ToolDefinition:
    """Create a ToolDefinition that searches the web for medical information."""

    ddg = DuckDuckGoSearchProvider()

    tavily: TavilySearchProvider | None = None
    if tavily_api_key:
        tavily = TavilySearchProvider(tavily_api_key)

    pubmed = PubMedSearchProvider()

    async def _handler(
        query: str,
        search_type: str = "general",
        max_results: int = 5,
        **_kwargs: Any,
    ) -> dict:
        if search_type == "academic":
            results = await pubmed.search(query, max_results=max_results)
        elif search_type in ("general", "drug"):
            domains = DRUG_DOMAINS if search_type == "drug" else MEDICAL_DOMAINS
            # Try DuckDuckGo first (free), fall back to Tavily
            results = await ddg.search(
                query, max_results=max_results, allowed_domains=domains
            )
            if not results and tavily:
                logger.info("DDG returned 0 results, falling back to Tavily")
                results = await tavily.search(
                    query, max_results=max_results, include_domains=domains
                )
        else:
            return {
                "results": [],
                "count": 0,
                "error": (
                    f"Unknown search_type: {search_type}. "
                    "Use 'general', 'academic', or 'drug'."
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
            '- "academic": Search PubMed for peer-reviewed medical literature (DEFAULT)\n'
            '- "general": Search trusted medical websites (Mayo Clinic, CDC, NIH, etc.)\n'
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
