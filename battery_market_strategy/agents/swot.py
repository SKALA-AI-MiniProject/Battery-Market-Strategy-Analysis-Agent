from __future__ import annotations

import logging

from .base import BaseAgent
from ..reference_utils import sanitize_references
from ..schemas import SWOTOutput
from ..state_models import GraphState
from ..services import LLMService

logger = logging.getLogger(__name__)


class SWOTAgent(BaseAgent):
    def __init__(
        self,
        llm_service: LLMService,
        name: str,
        company: str,
        state_key: str,
        source_analysis_key: str,
    ) -> None:
        self._llm_service = llm_service
        self.name = name
        self.company = company
        self.state_key = state_key
        self.source_analysis_key = source_analysis_key

    def run(self, state: GraphState) -> dict:
        logger.info("Starting %s", self.name)
        market = state["market_analysis"]
        company_analysis = state[self.source_analysis_key]
        system_prompt = (
            "You are a battery industry strategy analyst. "
            "Produce a SWOT using only the supplied market and company evidence. "
            "Write all outputs in Korean."
        )
        user_prompt = (
            f"회사: {self.company}\n\n"
            f"시장 분석:\n{market['market_view']}\n"
            f"시장 근거:\n{chr(10).join(f'- {item}' for item in market['evidence'])}\n\n"
            f"회사 핵심 분석:\n핵심 기술력/경쟁력: {chr(10).join(f'- {item}' for item in company_analysis['core_competitiveness'])}\n"
            f"다각화 전략: {chr(10).join(f'- {item}' for item in company_analysis['diversification_strategy'])}\n"
            f"회사 근거: {chr(10).join(f'- {item}' for item in company_analysis['evidence'])}\n\n"
            "강점과 약점은 내부 요인, 기회와 위협은 외부 요인으로 구분해."
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, SWOTOutput)
        references = sanitize_references(market["references"] + company_analysis["references"])
        logger.info("Completed %s", self.name)
        return {
            self.state_key: {
                "company": self.company,
                "strengths": output.strengths,
                "weaknesses": output.weaknesses,
                "opportunities": output.opportunities,
                "threats": output.threats,
                "references": references,
                "ready": True,
            }
        }


class LGESSWOTAgent(SWOTAgent):
    def __init__(self, llm_service: LLMService) -> None:
        super().__init__(
            llm_service=llm_service,
            name="lges_swot_agent",
            company="LG Energy Solution",
            state_key="lges_swot",
            source_analysis_key="lges_core_analysis",
        )


class CATLSWOTAgent(SWOTAgent):
    def __init__(self, llm_service: LLMService) -> None:
        super().__init__(
            llm_service=llm_service,
            name="catl_swot_agent",
            company="CATL",
            state_key="catl_swot",
            source_analysis_key="catl_core_analysis",
        )
