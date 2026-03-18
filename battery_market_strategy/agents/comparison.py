from __future__ import annotations

import logging

from .base import BaseAgent
from ..reference_utils import sanitize_references
from ..schemas import ComparisonOutput
from ..state_models import GraphState
from ..services import LLMService

logger = logging.getLogger(__name__)


class StrategicComparisonAgent(BaseAgent):
    name = "strategic_comparison_agent"

    def __init__(self, llm_service: LLMService) -> None:
        self._llm_service = llm_service

    def run(self, state: GraphState) -> dict:
        logger.info("Starting StrategicComparisonAgent")
        system_prompt = (
            "You are a neutral strategist comparing LG Energy Solution and CATL. "
            "Use only the provided analysis inputs. Write all outputs in Korean. "
            "Focus on strategic trade-offs, asymmetries, and likely consequences rather than repeating summaries."
        )
        user_prompt = (
            "시장 분석:\n"
            f"{state['market_analysis']['market_view']}\n\n"
            "LGES 핵심 기술력:\n"
            f"{chr(10).join(f'- {item}' for item in state['lges_core_analysis']['core_competitiveness'])}\n\n"
            "LGES 다각화:\n"
            f"{chr(10).join(f'- {item}' for item in state['lges_core_analysis']['diversification_strategy'])}\n\n"
            "CATL 핵심 기술력:\n"
            f"{chr(10).join(f'- {item}' for item in state['catl_core_analysis']['core_competitiveness'])}\n\n"
            "CATL 다각화:\n"
            f"{chr(10).join(f'- {item}' for item in state['catl_core_analysis']['diversification_strategy'])}\n\n"
            "LGES SWOT:\n"
            f"Strengths={state['lges_swot']['strengths']}\nWeaknesses={state['lges_swot']['weaknesses']}\n"
            f"Opportunities={state['lges_swot']['opportunities']}\nThreats={state['lges_swot']['threats']}\n\n"
            "CATL SWOT:\n"
            f"Strengths={state['catl_swot']['strengths']}\nWeaknesses={state['catl_swot']['weaknesses']}\n"
            f"Opportunities={state['catl_swot']['opportunities']}\nThreats={state['catl_swot']['threats']}\n\n"
            "전략적 차이점, 강약점 비교, 종합 결론을 작성해.\n"
            "전략적 차이점은 1) 기술/제품 포지셔닝, 2) 지역/생산 전략, 3) 수익성·가격 경쟁, 4) 포트폴리오 확장 관점에서 도출하라.\n"
            "강약점 비교는 단순 재서술이 아니라 어떤 시장 환경에서 어느 회사가 상대적으로 유리한지까지 드러나야 한다.\n"
            "결론은 '누가 무조건 우위'가 아니라 조건부 우위와 향후 관찰 포인트를 포함해야 한다."
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, ComparisonOutput)
        references = sanitize_references(state["collected_references"])
        logger.info("Completed StrategicComparisonAgent")
        return {
            "comparison": {
                "strategic_differences": output.strategic_differences,
                "strengths_weaknesses_comparison": output.strengths_weaknesses_comparison,
                "conclusion": output.conclusion,
                "references": references,
                "ready": True,
            }
        }
