"""``web.search`` — lightweight web search (DuckDuckGo HTML, no API key).

Network-backed; unit tests stub the HTTP client.
"""

from __future__ import annotations

import re
from html import unescape

import httpx

from core.tools.base import RISK_READ_ONLY, Tool, ToolContext

_DDG_URL = "https://html.duckduckgo.com/html/"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def _strip(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


async def _search(query: str, max_results: int = 5, *, context: ToolContext) -> dict:
    del context  # unused
    results: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            response = await client.post(_DDG_URL, data={"q": query})
            response.raise_for_status()
        for match in list(_RESULT_RE.finditer(response.text))[:max_results]:
            url = match.group(1)
            title = _strip(match.group(2))
            snippet = _strip(match.group(3))
            results.append({"title": title, "url": url, "snippet": snippet})
    except httpx.HTTPError as exc:
        return {"query": query, "results": [], "error": f"search failed: {type(exc).__name__}"}
    return {"query": query, "results": results}


def web_search_tool() -> Tool:
    return Tool(
        name="web.search",
        description=(
            "Search the web and return a small list of result titles, URLs and snippets. "
            "Use when the answer depends on current or external information."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "description": "Search query."},
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        fn=_search,
        risk=RISK_READ_ONLY,
        timeout=20.0,
    )
