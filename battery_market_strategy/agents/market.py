from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from .base import BaseAgent
from ..execution_state import is_approved
from ..reference_utils import sanitize_references
from ..reflection_utils import filter_market_missing_dimensions
from ..schemas import MarketAnalysisOutput
from ..state_models import GraphState
from ..services import LLMService, WebSearchService

logger = logging.getLogger(__name__)


class MarketAnalysisAgent(BaseAgent):
    name = "market_analysis_agent"

    def __init__(self, llm_service: LLMService, web_search_service: WebSearchService) -> None:
        self._llm_service = llm_service
        self._web_search_service = web_search_service

    def run(self, state: GraphState) -> dict:
        if state["market_analysis"]["ready"] and is_approved(state["market_analysis"]["search_evaluation"]):
            logger.info("Skipping MarketAnalysisAgent because the previous result is approved")
            return {"market_analysis": state["market_analysis"]}

        logger.info("Starting MarketAnalysisAgent")
        refined_query = state["supervisor"]["refined_user_query"] or state["raw_user_query"]
        revision_guidance = ""
        missing_dimensions = state["market_analysis"]["reflection"]["missing_dimensions"]
        if "market_analysis" in state["supervisor"]["revision_requests"]:
            last_reason = state["market_analysis"]["search_evaluation"]["last_reason"]
            guidance_lines = [last_reason] + missing_dimensions
            revision_guidance = "\n\n이전 시도에서 보완이 필요했던 항목:\n" + "\n".join(
                f"- {item}" for item in sorted(set(item for item in guidance_lines if item))
            )
        search_queries = _build_market_search_queries(refined_query, missing_dimensions)
        snippets: list[str] = []
        for query in search_queries:
            snippets.extend(self._web_search_service.search(query, max_results=4))
        snippets = _dedupe_search_snippets(snippets)

        if not snippets:
            snippets.append("웹 검색 결과가 없어 외부 최신 시장 근거를 확보하지 못했습니다.")

        system_prompt = (
            "You are a battery market analyst preparing an evidence-grounded sector brief. "
            "Use only the provided search evidence and write all outputs in Korean. "
            "The market analysis must focus on industry structure first, not on company-by-company comparison. "
            "Use company names only as examples inside broader sector dynamics when necessary. "
            "Prioritize diverse, non-overlapping facts from distinct sources rather than repeating the same theme. "
            "Prefer concrete claims with numbers, dates, regions, policy names, product categories, or capacity/price indicators when available. "
            "Do not duplicate the same statistic, company example, or source across evidence bullets. "
            "Separate directly supported facts from your own inference, and if the evidence conflicts, acknowledge the tension instead of flattening it. "
            "Do not default to an optimistic narrative. Deliberately look for downside signals such as oversupply, margin pressure, policy delays, utilization weakness, demand slowdown, or execution risk when the evidence supports them. "
            "If the evidence set is mixed, represent both tailwinds and headwinds instead of summarizing only the positive side. "
            "Fill missing_dimensions with any missing coverage buckets among EV demand, ESS demand, policy/localization, pricing/profitability, supply/capacity, and risk/headwinds. "
            "Do not treat OEM-specific contracts, next-generation battery investment details, or raw-material supply chain minutiae as hard blockers when the broader market picture is already sufficient for a strategic report. "
            "Use recommended_action=retry_retrieve when source coverage is genuinely missing, and recommended_action=retry_rewrite when the evidence exists but the synthesis is repetitive or weak. "
            "Set revision_needed=True only when recommended_action is not accept."
        )
        user_prompt = (
            f"연구 목표:\n{refined_query}\n\n"
            "아래 웹 검색 근거를 바탕으로 배터리 산업 시장 분석을 작성해.\n"
            "반드시 EV 수요, ESS 수요, 지역별 정책/현지화, 가격 경쟁, 공급 과잉 또는 수익성 압박을 다뤄.\n"
            "market_view는 산업 전체 관점에서 2~3개 단락 분량으로 작성하고, 다음 흐름을 자연스럽게 포함해야 한다:\n"
            "1) 수요 구조 변화(EV vs ESS)\n"
            "2) 공급·가격·가동률 또는 수익성 압박\n"
            "3) 지역별 정책/현지화와 전략적 함의\n"
            "가능하면 서로 다른 출처와 서로 다른 사실을 기반으로 6개 이상의 evidence를 제시하고, 같은 출처에서 나온 유사 주장 반복은 피해야 한다.\n"
            "evidence와 market_view에는 시장 성장 요인만이 아니라, 최소 1~2개의 하방 요인 또는 제약 조건을 포함해 균형 있게 정리해.\n"
            "evidence는 단순 나열이 아니라 전략 보고서에 바로 인용 가능한 fact statement 형태로 써라.\n\n"
            f"검색 근거:\n{chr(10).join(f'- {item}' for item in snippets[:16])}\n\n"
            "각 evidence 항목은 측정 가능한 사실이나 구체 주장으로 쓰고, 동일한 내용의 재진술은 하나로 합쳐라."
            f"{revision_guidance}"
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, MarketAnalysisOutput)

        references = sanitize_references(_extract_references(snippets))
        agent_decision = {
            "focus": "market attractiveness and sector structure",
            "missing_points": output.missing_points,
            "bias_checks": output.bias_checks,
            "missing_dimensions": filter_market_missing_dimensions(output.missing_dimensions),
            "failure_type": output.failure_type,
            "recommended_action": output.recommended_action,
            "revision_needed": output.revision_needed or output.recommended_action != "accept",
        }
        logger.info(
            "Completed MarketAnalysisAgent evidence_count=%s agent_action=%s missing_dimensions=%s",
            len(output.evidence),
            agent_decision["recommended_action"],
            agent_decision["missing_dimensions"],
        )
        return {
            "market_analysis": {
                "market_view": output.market_view,
                "evidence": output.evidence,
                "references": references,
                "agent_decision": agent_decision,
                "search_evaluation": state["market_analysis"]["search_evaluation"],
                "reflection": state["market_analysis"]["reflection"],
                "ready": True,
            }
        }


def _extract_references(snippets: list[str]) -> list[str]:
    refs: list[str] = []
    for item in snippets:
        marker = "Source: "
        if marker in item:
            refs.append(item.rsplit(marker, 1)[-1].strip())
    return sorted(set(refs))


def _build_market_search_queries(refined_query: str, missing_dimensions: list[str]) -> list[str]:
    focus = refined_query.strip() or "battery market outlook"
    queries = [
        f"{focus} global EV battery demand outlook",
        f"{focus} global ESS battery demand outlook",
        f"{focus} China Europe North America battery policy localization",
        f"{focus} lithium ion battery pricing margin oversupply utilization",
        f"{focus} battery manufacturing capacity expansion competition",
        f"{focus} battery raw materials lithium pricing supply chain risks",
    ]
    targeted_queries = {
        "EV 수요": f"{focus} EV sales battery demand forecast",
        "ESS 수요": f"{focus} ESS deployment battery demand forecast",
        "정책/현지화": f"{focus} battery policy tariff localization incentives",
        "가격/수익성": f"{focus} battery cell price margin profitability trend",
        "공급/생산능력": f"{focus} battery capacity utilization oversupply expansion",
        "리스크/역풍": f"{focus} battery industry risks headwinds demand slowdown",
    }
    for dimension in missing_dimensions:
        query = targeted_queries.get(dimension)
        if query:
            queries.append(query)
    return list(dict.fromkeys(queries))


def _dedupe_search_snippets(snippets: list[str]) -> list[str]:
    deduped: list[str] = []
    seen_sources: set[str] = set()
    seen_content_keys: set[str] = set()
    for item in snippets:
        source = _extract_source(item)
        content_key = _normalize_content_key(item)
        if source and source in seen_sources:
            continue
        if content_key in seen_content_keys:
            continue
        deduped.append(item)
        if source:
            seen_sources.add(source)
        seen_content_keys.add(content_key)
    return deduped


def _extract_source(snippet: str) -> str:
    marker = "Source: "
    if marker not in snippet:
        return ""
    url = snippet.rsplit(marker, 1)[-1].strip()
    parsed = urlparse(url)
    return parsed.netloc.lower() or url.lower()


def _normalize_content_key(snippet: str) -> str:
    marker = "Source: "
    content = snippet.split(marker, 1)[0]
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    return normalized[:220]
