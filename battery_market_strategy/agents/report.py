from __future__ import annotations

import logging

from .base import BaseAgent
from ..execution_state import is_approved, update_search_evaluation
from ..reflection_utils import assess_report_output, build_reflection, reflection_action_to_verdict
from ..reference_utils import inject_references_section, render_references, sanitize_references
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
        revision_guidance = ""
        if "report" in state["supervisor"]["revision_requests"]:
            guidance_items = (
                [state["report"]["search_evaluation"]["last_reason"]]
                + state["report"]["reflection"]["missing_points"]
                + [item for item in state["supervisor"]["revision_requests"] if item != "report"]
            )
            revision_guidance = "\n보완 요청:\n" + "\n".join(f"- {item}" for item in sorted(set(guidance_items)))
        system_prompt = (
            "You are preparing a professional battery market strategy report in Korean. "
            "Use only the supplied analyses. Produce concise but information-dense markdown. "
            "Fill missing_dimensions with any absent required sections or coverage gaps. "
            "Use recommended_action=retry_rewrite when structure, grounding, or consistency is weak, and accept when the report is complete and coherent. "
            "Set revision_needed=True only when recommended_action is not accept."
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
            "References 섹션은 작성하지 마. 참고문헌은 시스템이 별도로 추가한다."
            f"{revision_guidance}"
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, ReportOutput)
        references = sanitize_references(state["collected_references"])
        rendered_references = render_references(references)
        markdown_body = inject_references_section(output.markdown_body, references)
        markdown_path, pdf_path = self._report_service.save_report(output.title, markdown_body)
        quality_check = {
            "has_summary": bool(output.summary.strip()),
            "has_references": bool(references),
            "summary_is_consistent": output.summary.strip() in markdown_body or "Executive Summary" in markdown_body,
            "references_are_relevant": all(item in markdown_body for item in rendered_references) and "## References" in markdown_body,
        }
        rule_reflection = assess_report_output(output, markdown_body, references, quality_check)
        reflection = build_reflection(
            focus="report quality check before PDF generation",
            llm_missing_points=output.missing_points,
            llm_bias_checks=output.bias_checks,
            llm_missing_dimensions=output.missing_dimensions,
            llm_failure_type=output.failure_type,
            llm_action=output.recommended_action,
            rule_missing_points=rule_reflection["missing_points"],
            rule_bias_checks=rule_reflection["bias_checks"],
            rule_missing_dimensions=rule_reflection["missing_dimensions"],
            rule_failure_type=rule_reflection["failure_type"],
            rule_action=rule_reflection["recommended_action"],
        )
        reason = "; ".join(reflection["missing_points"]) if reflection["missing_points"] else "report quality approved"
        search_evaluation = update_search_evaluation(
            state["report"]["search_evaluation"],
            verdict=reflection_action_to_verdict(reflection["recommended_action"]),
            last_reason=reason,
        )
        logger.info(
            "Completed PDFReportAgent pdf=%s verdict=%s action=%s missing_dimensions=%s retry_count=%s revision_count=%s reason=%s quality_check=%s",
            pdf_path,
            search_evaluation["verdict"],
            reflection["recommended_action"],
            reflection["missing_dimensions"],
            search_evaluation["retry_count"],
            search_evaluation["revision_count"],
            search_evaluation["last_reason"],
            quality_check,
        )
        return {
            "report": {
                "title": output.title,
                "summary": output.summary,
                "markdown_path": markdown_path,
                "pdf_path": pdf_path,
                "references": references,
                "quality_check": quality_check,
                "search_evaluation": search_evaluation,
                "reflection": reflection,
                "ready": True,
            }
        }
