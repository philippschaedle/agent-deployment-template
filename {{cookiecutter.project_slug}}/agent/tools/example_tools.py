import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from agent.observability import instrument
from agent.tools.response_models import SearchResult


@instrument
def get_current_datetime() -> str:
    """Return the current UTC date and time as an ISO 8601 string."""
    return datetime.now(tz=UTC).isoformat()


@instrument
def web_search(query: str) -> list[SearchResult]:
    """Search the web and return a list of relevant results.

    Args:
        query: The search query string.

    Returns:
        A list of search results with title, URL, and snippet.
    """
    api_key = os.getenv("SERPAPI_API_KEY")
    if api_key:
        return _serpapi_search(query, api_key)
    return [
        SearchResult(
            title="Search stub — set SERPAPI_API_KEY to enable live results",
            url="https://serpapi.com",
            snippet=(
                f"Stub result for query: '{query}'. "
                "Add SERPAPI_API_KEY to .env to enable real web search."
            ),
        )
    ]


def _serpapi_search(query: str, api_key: str) -> list[SearchResult]:
    params = urllib.parse.urlencode(
        {"q": query, "api_key": api_key, "engine": "google", "num": "5"}
    )
    url = f"https://serpapi.com/search?{params}"
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        data = json.loads(resp.read())
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("link", ""),
            snippet=r.get("snippet", ""),
        )
        for r in data.get("organic_results", [])[:5]
    ]
