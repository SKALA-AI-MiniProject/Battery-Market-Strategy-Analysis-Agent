from __future__ import annotations

import logging

from .base import BaseAgent
from ..execution_state import is_approved
from ..reference_utils import inject_references_section, render_references, sanitize_references
from ..schemas import PDFReadyMarkdownOutput, ReportOutput
from ..spec import DEFAULT_REPORT_TITLE
from ..state_models import GraphState
from ..services import LLMService, ReportService

logger = logging.getLogger(__name__)

# PDF 렌더러 입력용 마크다운 정규화 프롬프트
PDF_CONVERSION_SYSTEM_PROMPT = """You are a document normalization module for PDF generation. Your only job is to rewrite the given report markdown so that it conforms to a strict, PDF-renderer-friendly format. Do not add or remove factual content; only adjust structure and formatting.

Allowed markdown elements (use only these):
- Section headings: exactly "## " followed by the section title (no ### or other levels).
- Tables: rows starting with "|", with header row and optional separator row (|---|---|). Keep tables simple; avoid merged cells or complex layouts that break PDF layout.
- Bullet lists: lines starting with "- " (hyphen space).
- Body paragraphs: plain text lines. Use short paragraphs to avoid overflow in PDF.

Forbidden (will break or be ignored by the PDF renderer):
- Inline HTML, code blocks with triple backticks, images, or links with markdown link syntax. For references, list URLs or identifiers as plain text or in a simple bullet list under ## References.
- Headings other than ## (no #, ###, ####).
- Nested lists or numbered lists; use only "- " bullets if lists are needed.

Output: Return only the normalized markdown body. No commentary, no code fence. The text must be valid UTF-8 and suitable for A4 PDF with standard margins. Preserve all section titles and the order: Executive Summary, Market Analysis, LG Energy Solution, CATL, SWOT Comparison, Strategic Conclusion, References."""

PDF_CONVERSION_USER_TEMPLATE = """Normalize the report markdown below for PDF conversion. Do not change the content; only adjust the structure to the allowed format (## headings, | tables, - bullets, plain paragraphs).

Input markdown:
---
{markdown_body}
---
Output: Return only the normalized markdown body (no code fence or commentary)."""


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
        market_source_pool = "; ".join(render_references(state["market_analysis"]["references"])) or "없음"
        lges_source_pool = "; ".join(render_references(state["lges_core_analysis"]["references"])) or "없음"
        catl_source_pool = "; ".join(render_references(state["catl_core_analysis"]["references"])) or "없음"
        comparison_source_pool = "; ".join(render_references(state["comparison"]["references"])) or "없음"
        system_prompt = (
            "You are preparing a professional battery market strategy report in Korean. "
            "Use only the supplied analyses. Produce a board-style strategy report in Korean. "
            "The report should feel analytical, evidence-aware, and decision-oriented rather than like a short summary. "
            "Every major section should explain not only what is true, but why it matters strategically. "
            "Do not write generic filler, broad praise, or unsupported superlatives. "
            "Use short source-note lines such as '근거 출처: ...' inside sections when useful, drawing only from the provided source pools. "
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
            "- 3~4개 bullet로 핵심 인사이트, 경쟁 구도, 전략적 시사점을 요약\n"
            "## Market Analysis\n"
            "- 산업 관점에서 수요 구조, 공급/가격, 정책/현지화, 전략적 함의를 서술\n"
            "- 회사 비교가 아니라 산업 레벨 분석이 중심이어야 함\n"
            "- 마지막에 '근거 출처:' 한 줄 추가\n"
            "## LG Energy Solution\n"
            "- Core Competitiveness, Portfolio Diversification, Risks/Constraints, Strategic Implication을 구분해 서술\n"
            "- 강점 나열이 아니라 근거 기반 설명과 전략적 의미를 포함\n"
            "- 마지막에 '근거 출처:' 한 줄 추가\n"
            "## CATL\n"
            "- Core Competitiveness, Portfolio Diversification, Risks/Constraints, Strategic Implication을 구분해 서술\n"
            "- 강점 나열이 아니라 근거 기반 설명과 전략적 의미를 포함\n"
            "- 마지막에 '근거 출처:' 한 줄 추가\n"
            "## SWOT Comparison\n"
            "- 표만 반복하지 말고, 어떤 시장 조건에서 어느 회사가 유리한지 2~4개 bullet로 비교 분석\n"
            "## Strategic Conclusion\n"
            "- 단순 요약이 아니라 회사별 권고안, 관찰 포인트, 우위가 바뀔 수 있는 조건을 포함\n"
            "References 섹션은 작성하지 마. 참고문헌은 시스템이 별도로 추가한다."
            f"\n\n시장 섹션 source pool:\n{market_source_pool}"
            f"\n\nLGES 섹션 source pool:\n{lges_source_pool}"
            f"\n\nCATL 섹션 source pool:\n{catl_source_pool}"
            f"\n\n비교/결론 source pool:\n{comparison_source_pool}"
            f"{revision_guidance}"
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, ReportOutput)
        references = sanitize_references(state["collected_references"])
        rendered_references = render_references(references)
        markdown_body = inject_references_section(output.markdown_body, references)

        try:
            pdf_user = PDF_CONVERSION_USER_TEMPLATE.format(markdown_body=markdown_body)
            pdf_ready = self._llm_service.invoke_structured(
                PDF_CONVERSION_SYSTEM_PROMPT, pdf_user, PDFReadyMarkdownOutput
            )
            body_for_pdf = pdf_ready.markdown_body
        except Exception as exc:
            logger.warning("PDF conversion prompt step failed, using original markdown: %s", exc)
            body_for_pdf = markdown_body

        markdown_path, pdf_path = self._report_service.save_report(output.title, body_for_pdf)
        quality_check = {
            "has_summary": bool(output.summary.strip()),
            "has_references": bool(references),
            "summary_is_consistent": output.summary.strip() in markdown_body or "Executive Summary" in markdown_body,
            "references_are_relevant": all(item in markdown_body for item in rendered_references) and "## References" in markdown_body,
        }
        agent_decision = {
            "focus": "report quality check before PDF generation",
            "missing_points": output.missing_points,
            "bias_checks": output.bias_checks,
            "missing_dimensions": output.missing_dimensions,
            "failure_type": output.failure_type,
            "recommended_action": output.recommended_action,
            "revision_needed": output.revision_needed or output.recommended_action != "accept",
        }
        logger.info(
            "Completed PDFReportAgent pdf=%s agent_action=%s missing_dimensions=%s quality_check=%s",
            pdf_path,
            agent_decision["recommended_action"],
            agent_decision["missing_dimensions"],
            quality_check,
        )
        return {
            "report": {
                "title": output.title,
                "summary": output.summary,
                "markdown_body": markdown_body,
                "markdown_path": markdown_path,
                "pdf_path": pdf_path,
                "references": references,
                "quality_check": quality_check,
                "agent_decision": agent_decision,
                "search_evaluation": state["report"]["search_evaluation"],
                "reflection": state["report"]["reflection"],
                "ready": True,
            }
        }
