from __future__ import annotations

from dataclasses import dataclass
import logging
from urllib.parse import urlparse

import requests
from tavily import TavilyClient

from ..config import AppConfig

logger = logging.getLogger(__name__)


_BLOCKED_DOMAIN_SUFFIXES = (
    "tistory.com",
    "medium.com",
    "substack.com",
    "linkedin.com",
    "youtube.com",
    "reddit.com",
    "wordpress.com",
    "blogspot.com",
    "naver.com",
)

_TRUSTED_DOMAIN_SUFFIXES = (
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "apnews.com",
    "iea.org",
    "lgensol.com",
    "catl.com",
    "sec.gov",
    "energy.gov",
    "europa.eu",
)

_COMPANY_TOKENS = {
    "LG Energy Solution": ("lg energy solution", "lges", "lgensol"),
    "CATL": ("catl", "contemporary amperex"),
}


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    content: str
    url: str
    domain: str
    trust_score: int


class WebSearchService:
    def __init__(self, config: AppConfig) -> None:
        self._client = TavilyClient(api_key=config.tavily_api_key) if config.tavily_api_key else None
        if self._client is None:
            logger.warning("Tavily API key is not configured. Web search will return no results.")

    def search(self, query: str, max_results: int = 5) -> list[str]:
        structured_results = self.search_structured(query, max_results=max_results)
        return [self._format_result(item) for item in structured_results]

    def search_structured(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        if self._client is None:
            return []
        logger.info("Running web search query=%s max_results=%s", query, max_results)
        try:
            response = self._client.search(query=query, max_results=max_results)
        except requests.RequestException as exc:
            logger.warning("Web search failed query=%s reason=%s", query, exc)
            return []
        except Exception as exc:
            logger.warning("Unexpected web search failure query=%s reason=%s", query, exc)
            return []
        results = response.get("results", [])
        formatted: list[WebSearchResult] = []
        for item in results:
            title = item.get("title", "")
            content = item.get("content", "")
            url = item.get("url", "")
            domain = urlparse(url).netloc.lower()
            formatted.append(
                WebSearchResult(
                    title=title,
                    content=content,
                    url=url,
                    domain=domain,
                    trust_score=self._score_domain(domain),
                )
            )
        return formatted

    def search_trusted_company_results(self, company: str, query: str, max_results: int = 8) -> list[WebSearchResult]:
        candidates = self.search_structured(query, max_results=max_results)
        filtered = [item for item in candidates if self._is_trusted_company_result(item, company)]
        filtered.sort(key=lambda item: (-item.trust_score, item.domain, item.url))

        deduped: list[WebSearchResult] = []
        seen_domains: set[str] = set()
        for item in filtered:
            if item.domain in seen_domains:
                continue
            deduped.append(item)
            seen_domains.add(item.domain)
        return deduped[:4]

    @staticmethod
    def _format_result(item: WebSearchResult) -> str:
        return f"{item.title}\n{item.content}\nSource: {item.url}"

    def _is_trusted_company_result(self, item: WebSearchResult, company: str) -> bool:
        domain = item.domain
        if not domain:
            return False
        if any(domain.endswith(blocked) for blocked in _BLOCKED_DOMAIN_SUFFIXES):
            return False
        if not self._is_trusted_domain(domain):
            return False

        combined = f"{item.title}\n{item.content}\n{item.url}".lower()
        tokens = _COMPANY_TOKENS.get(company, (company.lower(),))
        return any(token in combined for token in tokens)

    def _is_trusted_domain(self, domain: str) -> bool:
        if domain.endswith((".gov", ".gov.uk", ".go.kr")):
            return True
        return any(domain.endswith(suffix) for suffix in _TRUSTED_DOMAIN_SUFFIXES)

    def _score_domain(self, domain: str) -> int:
        if domain.endswith(("lgensol.com", "catl.com", ".gov", ".gov.uk", ".go.kr")):
            return 3
        if domain.endswith(("reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com", "apnews.com")):
            return 2
        if domain.endswith(("iea.org", "energy.gov", "europa.eu", "sec.gov")):
            return 2
        if any(domain.endswith(suffix) for suffix in _TRUSTED_DOMAIN_SUFFIXES):
            return 1
        return 0
