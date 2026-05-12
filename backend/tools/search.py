"""
Web search tool for the Writer agent.
Uses Tavily if API key is available, falls back to a no-op gracefully.
"""

import os
from typing import List, Optional


def web_search(query: str, max_results: int = 3) -> List[dict]:
    """
    Search the web for relevant information.
    Returns list of {title, content, url} dicts.
    Returns empty list if Tavily key is not configured (Phase 1 fallback).
    """
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key or api_key.startswith("tvly-placeholder"):
        # No key available — writer will use its training knowledge
        return []

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        results = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
        )
        return [
            {
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", ""),
            }
            for r in results.get("results", [])
        ]
    except Exception as e:
        # If search fails, continue without it — the writer will use base knowledge
        print(f"[Search] Búsqueda web no disponible: {e}")
        return []
