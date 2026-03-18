from __future__ import annotations

import logging

from .base import BaseAgent
from ..reference_utils import sanitize_references
from ..execution_state import is_approved, update_search_evaluation
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
        if "market_analysis" in state["supervisor"]["revision_requests"]:
            last_reason = state["market_analysis"]["search_evaluation"]["last_reason"]
            revision_guidance = f"\n\n이전 시도에서 보완이 필요했던 항목:\n- {last_reason}"
        search_queries = [
            "global battery market EV ESS demand outlook battery industry",
            "battery industry North America Europe China policy price competition ESS",
            "lithium ion battery market oversupply utilization ESS growth outlook",
        ]
        snippets: list[str] = []
        for query in search_queries:
            snippets.extend(self._web_search_service.search(query, max_results=4))

        if not snippets:
            snippets.append("웹 검색 결과가 없어 외부 최신 시장 근거를 확보하지 못했습니다.")

        system_prompt = (
            "You are a battery market analyst. Use only the provided search evidence. "
            "Write all outputs in Korean. Keep claims concrete and objective."
        )
        user_prompt = (
            f"연구 목표:\n{refined_query}\n\n"
            "아래 웹 검색 근거를 바탕으로 배터리 산업 시장 분석을 작성해.\n"
            "반드시 EV 수요, ESS 수요, 지역별 정책/현지화, 가격 경쟁, 공급 과잉 또는 수익성 압박을 다뤄.\n\n"
            f"검색 근거:\n{chr(10).join(f'- {item}' for item in snippets[:12])}\n\n"
            "각 evidence 항목은 측정 가능한 사실이나 구체 주장으로 써."
            f"{revision_guidance}"
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, MarketAnalysisOutput)

        references = sanitize_references(_extract_references(snippets))
        verdict = "revise" if output.revision_needed else "approved"
        reason = "; ".join(output.missing_points) if output.missing_points else "reflection approved"
        search_evaluation = update_search_evaluation(
            state["market_analysis"]["search_evaluation"],
            verdict=verdict,
            last_reason=reason,
        )
        logger.info(
            "Completed MarketAnalysisAgent evidence_count=%s verdict=%s retry_count=%s revision_count=%s reason=%s",
            len(output.evidence),
            search_evaluation["verdict"],
            search_evaluation["retry_count"],
            search_evaluation["revision_count"],
            search_evaluation["last_reason"],
        )
        return {
            "market_analysis": {
                "market_view": output.market_view,
                "evidence": output.evidence,
                "references": references,
                "search_evaluation": search_evaluation,
                "reflection": {
                    "focus": "market attractiveness and sector structure",
                    "missing_points": output.missing_points,
                    "bias_checks": output.bias_checks,
                    "revision_needed": output.revision_needed,
                },
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
