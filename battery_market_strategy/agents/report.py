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

Structure preservation rules:
- Keep Executive Summary as a short paragraph block, not bullets.
- Keep Market Analysis as bullets only after its heading.
- Keep LG Energy Solution and CATL sections as bullets only after each heading.
- Preserve the SWOT Comparison section as a 3-column markdown table with rows for 강점, 약점, 기회, 위협.
- Keep Strategic Conclusion as one compact paragraph, not a table.
- Preserve the References section as bullet items only.

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
            "Use only the supplied analyses. Produce a board-style strategy report in Korean that follows an executive briefing layout. "
            "The report should read like a strategy document, not a generic essay. "
            "Prefer short blocks, compact bullets, and structured comparison over long narrative paragraphs. "
            "Every major section should explain what the fact is, why it matters, and when that advantage or risk is likely to matter. "
            "Do not write generic filler, broad praise, or unsupported superlatives. "
            "Maintain internal consistency across sections. Do not let SWOT contradict the company analysis unless the trade-off is explicitly explained. "
            "Distinguish clearly between established current capabilities, announced plans/targets, and your own strategic interpretation. "
            "If an item is a target, expansion plan, or management aspiration, write it as a plan or target rather than as a secured outcome. "
            "Do not overstate patent counts, capacity announcements, or market-share ambitions unless they are tied to execution, monetization, or defensibility. "
            "Use short source-note lines such as '근거 출처: ...' only when explicitly requested by the section format, drawing only from the provided source pools. "
            "Fill missing_dimensions with any absent required sections or coverage gaps. "
            "However, do not mark the draft as needing revision only because some quantification is missing if the analysis is still coherent and decision-useful. "
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
            "다음 구조를 갖는 markdown_body를 작성해. 형식을 반드시 지켜라:\n"
            "## Executive Summary\n"
            "- bullet를 쓰지 말고 하나의 짧은 문단으로 작성한다.\n"
            "- 4~5문장 이내에서 시장 환경, LGES 포지션, CATL 포지션, 조건부 우위를 요약한다.\n"
            "- 샘플처럼 상단 SUMMARY 박스에 들어가는 문안이라고 생각하고, 문장을 짧고 단단하게 쓴다.\n"
            "\n"
            "## Market Analysis\n"
            "- 이 섹션은 bullet만 사용한다. 자유 서술 문단은 쓰지 마라.\n"
            "- 4~6개 bullet를 작성하고, 각 bullet는 '짧은 라벨: 내용' 형식으로 시작한다.\n"
            "- 최소한 EV 수요, ESS 성장, 가격/수익성 압박, 정책/현지화, 전략적 함의를 포함한다.\n"
            "- 회사별 설명이 아니라 산업 구조 변화 중심으로 써라.\n"
            "- 마지막 bullet는 '근거 출처: ...' 형식으로 작성한다.\n"
            "\n"
            "## LG Energy Solution\n"
            "- 이 섹션은 bullet만 사용한다. 자유 서술 문단은 쓰지 마라.\n"
            "- 6~8개 bullet를 작성한다.\n"
            "- 각 bullet는 반드시 '소주제: 내용' 형식으로 시작한다. 예: '북미 현지화: ...', '케미스트리 다각화: ...'.\n"
            "- 반드시 핵심 경쟁력, 생산/현지화 실행, 포트폴리오 다각화, 리스크/제약, 전략적 의미를 모두 포함한다.\n"
            "- 사실, 목표, 해석을 섞지 마라. 목표나 투자 계획이면 '계획', '목표', '예정'이라고 명시하라.\n"
            "- 중복되는 칭찬식 표현을 피하고, 근거가 약한 항목은 단정하지 마라.\n"
            "- 마지막 bullet는 '근거 출처: ...' 형식으로 작성한다.\n"
            "\n"
            "## CATL\n"
            "- 이 섹션은 bullet만 사용한다. 자유 서술 문단은 쓰지 마라.\n"
            "- 6~8개 bullet를 작성한다.\n"
            "- 각 bullet는 반드시 '소주제: 내용' 형식으로 시작한다. 예: 'ESS 글로벌 리더십: ...', '원가 경쟁력: ...'.\n"
            "- 반드시 핵심 경쟁력, 생산/원가 구조, 포트폴리오 다각화, 리스크/제약, 전략적 의미를 모두 포함한다.\n"
            "- 사실, 목표, 해석을 섞지 마라. 목표나 투자 계획이면 '계획', '목표', '예정'이라고 명시하라.\n"
            "- 마지막 bullet는 '근거 출처: ...' 형식으로 작성한다.\n"
            "\n"
            "## SWOT Comparison\n"
            "- 이 섹션은 반드시 markdown 표로 작성한다.\n"
            "- 표 컬럼은 정확히 '| 구분 | LG에너지솔루션 | CATL |' 로 시작한다.\n"
            "- 행은 정확히 강점, 약점, 기회, 위협 4개만 사용한다.\n"
            "- 각 셀은 키워드 나열이 아니라 1~2개의 짧은 완결 문장으로 작성한다.\n"
            "- 세미콜론(;)으로 끊은 압축 표현은 사용하지 마라.\n"
            "- 각 셀은 '무엇이 강점/약점/기회/위협인지 + 왜 전략적으로 중요한지'가 드러나야 한다.\n"
            "- 강점/약점은 내부 요인, 기회/위협은 외부 요인만 넣어라.\n"
            "- 같은 요소를 강점과 약점 양쪽에 중복 배치하지 마라. 만약 trade-off가 있으면 이유가 드러나게 다른 표현으로 정리하라.\n"
            "- 이 표는 이후 비교 시각화의 직접 입력이 되므로 형식을 깨지 마라.\n"
            "\n"
            "## Strategic Conclusion\n"
            "- bullet를 쓰지 말고 하나의 압축된 문단으로 작성한다.\n"
            "- 4~6문장으로 쓰며, '첫째, 둘째, 셋째'처럼 시사점을 구분해도 된다.\n"
            "- 반드시 LGES가 유리한 조건, CATL이 유리한 조건, 공통 리스크, 향후 관찰 포인트를 포함한다.\n"
            "- 결론은 확정적 우열이 아니라 조건부 우위, 병목, 판단을 바꿀 수 있는 변수까지 포함해야 한다.\n"
            "\n"
            "## References\n"
            "- 직접 작성한다.\n"
            "- bullet 리스트만 사용하고, 실제 URL 또는 PDF 페이지 식별자만 넣는다.\n"
            "- 근거 출처 bullet와 중복되더라도 최종 참고문헌 목록은 유지한다."
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
