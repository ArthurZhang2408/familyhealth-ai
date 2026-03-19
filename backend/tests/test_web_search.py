"""Tests for web search providers and the web_search agent tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agents.tools.web_search import build_web_search_tool
from app.services.web_search import (
    DuckDuckGoSearchProvider,
    PubMedSearchProvider,
    TavilySearchProvider,
)

# ===================================================================
# Tavily provider tests
# ===================================================================

TAVILY_RESPONSE = {
    "results": [
        {
            "title": "Metformin Side Effects - Mayo Clinic",
            "url": "https://www.mayoclinic.org/drugs/metformin/side-effects",
            "content": (
                "Common side effects of metformin include nausea, "
                "vomiting, stomach upset, diarrhea."
            ),
            "published_date": "2025-01-15",
        },
        {
            "title": "Metformin - MedlinePlus",
            "url": "https://medlineplus.gov/druginfo/meds/a696005.html",
            "content": "Metformin is used to treat type 2 diabetes.",
        },
    ]
}


@pytest.mark.asyncio
async def test_tavily_search_success():
    provider = TavilySearchProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = TAVILY_RESPONSE

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search("metformin side effects", max_results=5)

    assert len(results) == 2
    assert results[0].title == "Metformin Side Effects - Mayo Clinic"
    assert results[0].source == "mayoclinic.org"
    assert results[0].published_date == "2025-01-15"
    assert results[1].url == "https://medlineplus.gov/druginfo/meds/a696005.html"


@pytest.mark.asyncio
async def test_tavily_search_rate_limit():
    provider = TavilySearchProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Rate limit", request=MagicMock(), response=mock_response
    )

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_tavily_search_timeout():
    provider = TavilySearchProvider(api_key="test-key")

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("Timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_tavily_passes_domain_filter():
    provider = TavilySearchProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await provider.search("test", allowed_domains=["mayoclinic.org", "cdc.gov"])

        call_args = mock_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["include_domains"] == ["mayoclinic.org", "cdc.gov"]
        assert payload["search_depth"] == "advanced"


# ===================================================================
# DuckDuckGo provider tests
# ===================================================================

DDG_HTML_TWO_RESULTS = """
<div class="result">
  <h2 class="result__title">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.mayoclinic.org%2Fulcer">
      Peptic ulcer - Mayo Clinic</a>
  </h2>
  <a class="result__snippet" href="https://www.mayoclinic.org/ulcer">
    A <b>peptic</b> ulcer is a sore on the lining of your stomach.</a>
</div>
<div class="result">
  <h2 class="result__title">
    <a class="result__a" href="https://www.drugs.com/ibuprofen.html">
      Ibuprofen Uses &amp; Side Effects</a>
  </h2>
  <a class="result__snippet" href="https://www.drugs.com/ibuprofen.html">
    Ibuprofen is used to reduce fever and treat pain.</a>
</div>
<div class="result">
  <h2 class="result__title">
    <a class="result__a" href="https://www.reddit.com/r/health/ulcer">
      My ulcer experience - Reddit</a>
  </h2>
  <a class="result__snippet" href="https://www.reddit.com/r/health/ulcer">
    Just wanted to share my story about stomach ulcers.</a>
</div>
"""

DDG_HTML_EMPTY = "<html><body><div class='no-results'>No results</div></body></html>"


@pytest.mark.asyncio
async def test_ddg_search_success():
    provider = DuckDuckGoSearchProvider()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = DDG_HTML_TWO_RESULTS

    with patch("app.services.web_search.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await provider.search("peptic ulcer", max_results=5)

    assert len(results) == 3
    assert results[0].title == "Peptic ulcer - Mayo Clinic"
    assert results[0].url == "https://www.mayoclinic.org/ulcer"
    assert results[0].source == "mayoclinic.org"
    assert "peptic" in results[0].snippet.lower()
    assert results[1].title == "Ibuprofen Uses & Side Effects"


@pytest.mark.asyncio
async def test_ddg_search_domain_filtering():
    provider = DuckDuckGoSearchProvider()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = DDG_HTML_TWO_RESULTS

    with patch("app.services.web_search.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await provider.search(
            "ulcer",
            allowed_domains=["mayoclinic.org", "cdc.gov"],
        )

    # Only mayoclinic.org should pass; drugs.com and reddit filtered out
    assert len(results) == 1
    assert results[0].source == "mayoclinic.org"


@pytest.mark.asyncio
async def test_ddg_search_empty_results():
    provider = DuckDuckGoSearchProvider()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = DDG_HTML_EMPTY

    with patch("app.services.web_search.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await provider.search("xyznonexistent")

    assert results == []


@pytest.mark.asyncio
async def test_ddg_search_timeout():
    provider = DuckDuckGoSearchProvider()

    with patch("app.services.web_search.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("Timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await provider.search("test")

    assert results == []


@pytest.mark.asyncio
async def test_ddg_search_max_results_cap():
    provider = DuckDuckGoSearchProvider()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = DDG_HTML_TWO_RESULTS

    with patch("app.services.web_search.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await provider.search("test", max_results=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_ddg_uddg_redirect_extraction():
    """DDG wraps URLs in //duckduckgo.com/l/?uddg=ENCODED_URL redirects."""
    provider = DuckDuckGoSearchProvider()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = DDG_HTML_TWO_RESULTS

    with patch("app.services.web_search.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await provider.search("test", max_results=5)

    # First result uses uddg redirect, should be extracted
    assert results[0].url == "https://www.mayoclinic.org/ulcer"
    # Second result is a direct URL
    assert results[1].url == "https://www.drugs.com/ibuprofen.html"


# ===================================================================
# PubMed provider tests
# ===================================================================

PUBMED_SEARCH_RESPONSE = {
    "esearchresult": {
        "idlist": ["12345678", "87654321"],
    }
}

PUBMED_SUMMARY_RESPONSE = {
    "result": {
        "uids": ["12345678", "87654321"],
        "12345678": {
            "title": "Metformin and cardiovascular outcomes: a systematic review",
            "authors": [
                {"name": "Smith J"},
                {"name": "Doe A"},
            ],
            "fulljournalname": "The Lancet",
            "pubdate": "2024 Mar",
            "source": "Lancet",
        },
        "87654321": {
            "title": "Type 2 diabetes management guidelines 2024",
            "authors": [{"name": "Johnson K"}],
            "fulljournalname": "JAMA Internal Medicine",
            "pubdate": "2024 Jun",
            "source": "JAMA Intern Med",
        },
    }
}


@pytest.mark.asyncio
async def test_pubmed_search_success():
    provider = PubMedSearchProvider(api_key="test-key")

    mock_search_resp = MagicMock()
    mock_search_resp.raise_for_status = MagicMock()
    mock_search_resp.json.return_value = PUBMED_SEARCH_RESPONSE

    mock_summary_resp = MagicMock()
    mock_summary_resp.raise_for_status = MagicMock()
    mock_summary_resp.json.return_value = PUBMED_SUMMARY_RESPONSE

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = [mock_search_resp, mock_summary_resp]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search("metformin cardiovascular")

    assert len(results) == 2
    assert results[0].title == "Metformin and cardiovascular outcomes: a systematic review"
    assert results[0].url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert results[0].source == "PubMed"
    assert "Smith J et al." in results[0].snippet
    assert "The Lancet" in results[0].snippet
    assert results[1].snippet == "Johnson K. JAMA Internal Medicine. 2024 Jun"


@pytest.mark.asyncio
async def test_pubmed_search_no_results():
    provider = PubMedSearchProvider()

    mock_search_resp = MagicMock()
    mock_search_resp.raise_for_status = MagicMock()
    mock_search_resp.json.return_value = {"esearchresult": {"idlist": []}}

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_search_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search("xyznonexistent12345")

    assert results == []


@pytest.mark.asyncio
async def test_pubmed_search_timeout():
    provider = PubMedSearchProvider()

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_pubmed_passes_api_key():
    provider = PubMedSearchProvider(api_key="my-ncbi-key")

    mock_search_resp = MagicMock()
    mock_search_resp.raise_for_status = MagicMock()
    mock_search_resp.json.return_value = {"esearchresult": {"idlist": []}}

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_search_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await provider.search("test")

        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params")
        assert params["api_key"] == "my-ncbi-key"


# ===================================================================
# Tool handler tests
# ===================================================================


@pytest.mark.asyncio
async def test_tool_handler_general_tries_ddg_first():
    """General search uses DDG first; if DDG succeeds, Tavily is not called."""
    tool = build_web_search_tool(tavily_api_key="test-key")

    ddg_html = (
        '<h2 class="result__title">'
        '<a class="result__a" href="https://cdc.gov/info">'
        "CDC Info</a></h2>"
        '<a class="result__snippet" href="https://cdc.gov/info">'
        "Health information from CDC</a>"
    )
    mock_ddg_resp = MagicMock()
    mock_ddg_resp.raise_for_status = MagicMock()
    mock_ddg_resp.text = ddg_html
    mock_ddg_resp.status_code = 200

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_ddg_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await tool.handler(query="test", search_type="general")

    assert result["count"] == 1
    assert result["results"][0]["title"] == "CDC Info"
    assert result["results"][0]["source"] == "cdc.gov"


@pytest.mark.asyncio
async def test_tool_handler_academic_routes_to_pubmed():
    tool = build_web_search_tool(tavily_api_key="")

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_search_resp = MagicMock()
        mock_search_resp.raise_for_status = MagicMock()
        mock_search_resp.json.return_value = {"esearchresult": {"idlist": ["11111"]}}

        mock_summary_resp = MagicMock()
        mock_summary_resp.raise_for_status = MagicMock()
        mock_summary_resp.json.return_value = {
            "result": {
                "uids": ["11111"],
                "11111": {
                    "title": "A Study",
                    "authors": [{"name": "Auth A"}],
                    "fulljournalname": "Nature",
                    "pubdate": "2024",
                    "source": "Nature",
                },
            }
        }

        mock_client = AsyncMock()
        mock_client.get.side_effect = [mock_search_resp, mock_summary_resp]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await tool.handler(query="diabetes study", search_type="academic")

    assert result["count"] == 1
    assert result["results"][0]["source"] == "PubMed"
    assert "pubmed.ncbi.nlm.nih.gov" in result["results"][0]["url"]


@pytest.mark.asyncio
async def test_tool_handler_ddg_fails_falls_back_to_tavily():
    """When DDG returns 0 results, Tavily is tried as fallback."""
    tool = build_web_search_tool(tavily_api_key="test-key")

    # DDG returns empty HTML (no results)
    ddg_resp = MagicMock()
    ddg_resp.raise_for_status = MagicMock()
    ddg_resp.text = "<html><body>No results</body></html>"
    ddg_resp.status_code = 200

    # Tavily returns results
    tavily_resp = MagicMock()
    tavily_resp.raise_for_status = MagicMock()
    tavily_resp.json.return_value = {
        "results": [
            {
                "title": "Drugs.com Info",
                "url": "https://drugs.com/ibuprofen",
                "content": "Ibuprofen info",
            }
        ]
    }

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        # First call = DDG (post), second call = Tavily (post)
        mock_client.post.side_effect = [ddg_resp, tavily_resp]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await tool.handler(query="ibuprofen dosage", search_type="drug")

    assert result["count"] == 1
    assert result["results"][0]["source"] == "drugs.com"


@pytest.mark.asyncio
async def test_tool_handler_no_tavily_key_ddg_still_works():
    """Without Tavily key, DDG still works as primary search."""
    tool = build_web_search_tool(tavily_api_key="")

    ddg_html = (
        '<a class="result__a" href="https://mayoclinic.org/test">'
        "Mayo Info</a>"
        '<a class="result__snippet" href="https://mayoclinic.org/test">'
        "Health info</a>"
    )
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = ddg_html
    mock_resp.status_code = 200

    with patch("app.services.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await tool.handler(query="test", search_type="general")

    assert result["count"] == 1


@pytest.mark.asyncio
async def test_tool_handler_invalid_search_type():
    tool = build_web_search_tool(tavily_api_key="test-key")

    result = await tool.handler(query="test", search_type="invalid")

    assert result["count"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_definition_properties():
    tool = build_web_search_tool(tavily_api_key="key")

    assert tool.name == "web_search"
    assert tool.terminal is False
    decl = tool.to_declaration()
    assert "query" in decl["parameters"]["properties"]
    assert "search_type" in decl["parameters"]["properties"]
    assert decl["parameters"]["properties"]["search_type"]["enum"] == [
        "general",
        "academic",
        "drug",
    ]
