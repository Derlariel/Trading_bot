"""Async client for the free GDELT DOC 2.0 API."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

URL = "https://api.gdeltproject.org/api/v2/doc/doc"


async def search_gdelt(query: str, limit: int = 25, timeout: float = 10) -> list[dict[str, Any]]:
    params = {"query": query, "mode": "artlist", "maxrecords": min(limit, 250), "format": "json", "sort": "datedesc"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(URL, params=params) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return []
    return [{"headline": article.get("title", ""), "url": article.get("url"), "source": article.get("domain"), "published_at": article.get("seendate"), "summary": article.get("socialimage", "")} for article in payload.get("articles", []) if article.get("title")]
