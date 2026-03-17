from __future__ import annotations

import logging

from tavily import TavilyClient

from ..config import AppConfig

logger = logging.getLogger(__name__)


class WebSearchService:
    def __init__(self, config: AppConfig) -> None:
        self._client = TavilyClient(api_key=config.tavily_api_key) if config.tavily_api_key else None
        if self._client is None:
            logger.warning("Tavily API key is not configured. Web search will return no results.")

    def search(self, query: str, max_results: int = 5) -> list[str]:
        if self._client is None:
            return []
        logger.info("Running web search query=%s max_results=%s", query, max_results)
        response = self._client.search(query=query, max_results=max_results)
        results = response.get("results", [])
        formatted = []
        for item in results:
            title = item.get("title", "")
            content = item.get("content", "")
            url = item.get("url", "")
            formatted.append(f"{title}\n{content}\nSource: {url}")
        return formatted
