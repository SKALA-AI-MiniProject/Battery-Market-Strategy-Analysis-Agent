from __future__ import annotations

import logging

from .base import BaseAgent
from ..execution_state import is_approved, update_search_evaluation
from ..schemas import ReportOutput
from ..spec import DEFAULT_REPORT_TITLE
from ..state_models import GraphState
from ..services import LLMService, ReportService

logger = logging.getLogger(__name__)


class PDFReportAgent(BaseAgent):
    name = "pdf_report_agent"

    def __init__(self, llm_service: LLMService, report_service: ReportService) -> None:
        self._llm_service = llm_service
        self._report_service = report_service

    def run(self, state: GraphState) -> dict:
        if state["report"]["ready"] and is_approved(state["report"]["search_evaluation"]):
            logger.info("Skipping PDFReportAgent because the previous result is approved")
            return {"report": state["report"]}

        logger.info("Starting PDFReportAgent")
        system_prompt = (
            "You are preparing a professional battery market strategy report in Korean. "
            "Use only the supplied analyses. Produce concise but information-dense markdown."
        )
        user_prompt = (
            f"제목 기본값: {DEFAULT_REPORT_TITLE}\n\n"
            f"시장 분석:\n{state['market_analysis']['market_view']}\n"
            f"시장 근거:\n{chr(10).join(f'- {item}' for item in state['market_analysis']['evidence'])}\n\n"
            f"LGES 핵심 분석:\n핵심 기술력={state['lges_core_analysis']['core_competitiveness']}\n"
            f"다각화={state['lges_core_analysis']['diversification_strategy']}\n\n"
            f"CATL 핵심 분석:\n핵심 기술력={state['catl_core_analysis']['core_competitiveness']}\n"
            f"다각화={state['catl_core_analysis']['diversification_strategy']}\n\n"
            f"LGES SWOT={state['lges_swot']}\n\n"
            f"CATL SWOT={state['catl_swot']}\n\n"
            f"비교 분석={state['comparison']}\n\n"
            "다음 구조를 갖는 markdown_body를 작성해:\n"
            "## Executive Summary\n"
            "## Market Analysis\n"
            "## LG Energy Solution\n"
            "## CATL\n"
            "## SWOT Comparison\n"
            "## Strategic Conclusion\n"
            "## References\n"
            "References 섹션에는 실제 참조 식별자나 URL만 나열해."
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, ReportOutput)
        markdown_path, pdf_path = self._report_service.save_report(output.title, output.markdown_body)
        references = sorted(
            set(
                output.references
                + state["market_analysis"]["references"]
                + state["lges_core_analysis"]["references"]
                + state["catl_core_analysis"]["references"]
                + state["comparison"]["references"]
            )
        )
        quality_check = {
            "has_summary": bool(output.summary.strip()),
            "has_references": bool(references),
            "summary_is_consistent": output.summary.strip() in output.markdown_body or "Executive Summary" in output.markdown_body,
            "references_are_relevant": "## References" in output.markdown_body,
        }
        revision_needed = output.revision_needed or not all(quality_check.values())
        reason = "; ".join(output.missing_points) if output.missing_points else "report quality approved"
        search_evaluation = update_search_evaluation(
            state["report"]["search_evaluation"],
            verdict="revise" if revision_needed else "approved",
            last_reason=reason,
        )
        logger.info("Completed PDFReportAgent pdf=%s", pdf_path)
        return {
            "report": {
                "title": output.title,
                "summary": output.summary,
                "markdown_path": markdown_path,
                "pdf_path": pdf_path,
                "references": references,
                "quality_check": quality_check,
                "search_evaluation": search_evaluation,
                "reflection": {
                    "focus": "report quality check before PDF generation",
                    "missing_points": output.missing_points,
                    "bias_checks": output.bias_checks,
                    "revision_needed": revision_needed,
                },
                "ready": True,
            }
        }
