from __future__ import annotations

import logging
from pathlib import Path
import re

from .base import BaseAgent
from ..config import AppConfig
from ..execution_state import is_approved
from ..reflection_utils import filter_company_missing_dimensions
from ..reference_utils import sanitize_references
from ..schemas import CompanyAnalysisOutput
from ..state_models import GraphState
from ..services import AgenticRAGService, CompanyVectorStoreService, LLMService, WebSearchService

logger = logging.getLogger(__name__)

_DECISION_ACTION_PRIORITY = {
    "accept": 0,
    "retry_rewrite": 1,
    "retry_retrieve": 2,
    "fail": 3,
}

_NON_BLOCKING_COMPANY_POINT_PATTERNS = (
    r"customer",
    r"고객사",
    r"market share",
    r"시장 점유율",
    r"competitor",
    r"경쟁사",
    r"strategic differences",
    r"strategic positioning",
    r"positioning",
    r"service expansion",
    r"서비스 확장",
    r"recycling.*profit",
    r"재활용.*수익성",
    r"supply chain.*specific",
    r"공급망.*구체",
    r"quantitative",
    r"정량",
    r"timeline",
    r"timeline",
    r"timelines",
)


def _has_minimum_company_analysis_signal(output: CompanyAnalysisOutput, references: list[str]) -> bool:
    return (
        len(output.core_competitiveness) >= 2
        and len(output.diversification_strategy) >= 2
        and len(output.evidence) >= 3
        and len(references) >= 3
    )


class CompanyCorePortfolioAgent(BaseAgent):
    def __init__(
        self,
        config: AppConfig,
        llm_service: LLMService,
        rag_service: AgenticRAGService,
        web_search_service: WebSearchService,
        vector_store_service: CompanyVectorStoreService,
        name: str,
        company: str,
        state_key: str,
        retrieval_state_key: str,
        company_id: str,
    ) -> None:
        self._config = config
        self._llm_service = llm_service
        self._rag_service = rag_service
        self._web_search_service = web_search_service
        self._vector_store_service = vector_store_service
        self.name = name
        self.company = company
        self.state_key = state_key
        self.retrieval_state_key = retrieval_state_key
        self.company_id = company_id

    def run(self, state: GraphState) -> dict:
        if state[self.state_key]["ready"] and is_approved(state[self.state_key]["search_evaluation"]):
            logger.info("Skipping %s because the previous result is approved", self.name)
            return {
                self.retrieval_state_key: state[self.retrieval_state_key],
                self.state_key: state[self.state_key],
            }

        logger.info("Starting %s", self.name)
        retrieval_state = state[self.retrieval_state_key]
        pdf_path = Path(retrieval_state["pdf_path"])
        index_dir = Path(retrieval_state["index_dir"])
        refined_query = state["supervisor"]["refined_user_query"] or state["raw_user_query"]
        revision_guidance = ""
        if self.state_key in state["supervisor"]["revision_requests"]:
            last_reason = state[self.state_key]["search_evaluation"]["last_reason"]
            guidance_lines = [last_reason] + state[self.state_key]["reflection"]["missing_dimensions"]
            revision_guidance = "\n\n이전 시도에서 보완이 필요했던 항목:\n" + "\n".join(
                f"- {item}" for item in sorted(set(item for item in guidance_lines if item))
            )

        index_result = self._vector_store_service.ensure_index(self.company_id, pdf_path, index_dir)
        rag_result = self._rag_service.run(self.company, refined_query, index_result.index_dir, retrieval_state["top_k"])
        trusted_web_results = self._collect_trusted_web_results(refined_query)
        chunk_preview = "\n\n".join(
            f"[{chunk['reference']}] {chunk['content'][:900]}" for chunk in rag_result.retrieved_chunks[:10]
        )
        web_preview = "\n\n".join(
            f"[{item.domain}] {item.title}\n{item.content}\nSource: {item.url}" for item in trusted_web_results
        ) or "신뢰 기준을 통과한 외부 웹 근거 없음"

        system_prompt = (
            "You are a corporate strategy analyst focused on battery companies. "
            "Use the provided company-PDF evidence as the primary source, and use trusted web evidence only as a secondary external validation layer. "
            "Write all outputs in Korean. "
            "Prefer non-overlapping points grounded in different sections or pages when the evidence allows it. "
            "Avoid repeating the same plant, customer, product line, or chemistry claim across multiple bullets unless the repetition adds a distinct strategic implication. "
            "Favor explicit facts with named technologies, applications, geographies, production footprints, customer programs, or portfolio moves over generic praise. "
            "Separate what the company document states directly from what you cautiously infer or externally validate. "
            "If a detail is not explicit in the company PDF, mark it as not clearly disclosed instead of treating it as a required blocker. "
            "Do not require competitor comparison, external market-share data, or financial metrics unless they are explicitly present in the supplied company PDF. "
            "Detailed customer names, service expansion, recycling strategy, or supply-chain specifics may be absent in a limited company PDF sample and should usually be treated as optional enrichment rather than hard blockers. "
            "Each core competitiveness point should explain both the fact and why it matters strategically. "
            "Each diversification point should specify the expansion direction, operating basis, and expected role in the portfolio. "
            "Use trusted web evidence only when it comes from high-confidence domains such as official company sites, government or public institutions, or major global news organizations. "
            "Do not rely on blogs, social posts, opinion summaries, or weak secondary commentary. "
            "Do not default to optimistic company framing. For each major strength or diversification claim, actively consider execution risk, constraints, delays, dependence, or downside conditions when the evidence supports them. "
            "If external trusted web evidence weakens or qualifies a company claim, reflect that tension rather than repeating the company-positive framing only. "
            "Fill missing_dimensions with any missing evidence buckets among technology/chemistry, manufacturing footprint, customer/product, ESS or non-EV expansion, and supply chain/recycling/service. "
            "Use recommended_action=retry_retrieve when the evidence itself is too narrow, and recommended_action=retry_rewrite when the evidence exists but the synthesis is repetitive or weak. "
            "Set revision_needed=True only when recommended_action is not accept."
        )
        user_prompt = (
            f"회사: {self.company}\n"
            f"연구 목표: {refined_query}\n\n"
            "아래는 회사 PDF에서 회수한 근거다. 이 근거만 사용해 핵심 기술력과 포트폴리오 다각화 전략을 정리해.\n"
            "핵심 기술력은 기술 경쟁력, 생산/고객/지역 실행력, 제품 포트폴리오를 포함하고,\n"
            "다각화 전략은 EV 외 확장, chemistry diversification, ESS, 공급망/재활용/서비스 확장을 포함해.\n"
            "가능하면 서로 다른 페이지의 근거를 활용해 3개 이상의 핵심 경쟁력 포인트와 3개 이상의 다각화 포인트를 도출하되,\n"
            "같은 사실을 표현만 바꿔 반복하지 마.\n"
            "핵심 기술력 각 항목은 '무엇을 보유/실행하는가 + 왜 전략적으로 중요한가'까지 포함해라.\n"
            "다각화 전략 각 항목은 '어느 영역으로 확장하는가 + 그 확장의 기반이 무엇인가'까지 포함해라.\n"
            "회사 PDF에 없는 정보를 웹 근거로 보강할 수는 있지만, 웹 근거는 PDF 주장을 검증·보완하는 수준으로만 사용하고 과장하지 마.\n"
            "핵심 경쟁력과 다각화 전략을 정리할 때, 가능하면 최소 1~2개의 제약 요인·실행 리스크·불확실성도 evidence에 포함해 일방적으로 긍정적인 서술을 피하라.\n"
            "evidence는 보고서 본문에서 바로 근거로 쓸 수 있도록 구체 fact statement 5개 이상을 목표로 하라.\n"
            "모든 결론은 보수적으로 정리하고, 확인된 사실과 해석을 섞지 마.\n\n"
            f"회사 PDF 근거:\n{chunk_preview}\n\n"
            f"신뢰도 필터를 통과한 외부 웹 근거:\n{web_preview}"
            f"{revision_guidance}"
        )
        output = self._llm_service.invoke_structured(system_prompt, user_prompt, CompanyAnalysisOutput)

        normalized_chunks = [
            {
                "chunk_id": item["chunk_id"],
                "page": item["page"],
                "score": item["score"],
                "content": item["content"],
            }
            for item in rag_result.retrieved_chunks
        ]
        references = sanitize_references(rag_result.references + [item.url for item in trusted_web_results])
        agent_action = _pick_stricter_action(output.recommended_action, rag_result.reflection.recommended_action)
        agent_failure_type = output.failure_type if output.failure_type != "none" else rag_result.reflection.failure_type
        filtered_missing_points = _filter_non_blocking_company_points(
            output.missing_points + rag_result.reflection.missing_points
        )
        filtered_missing_dimensions = filter_company_missing_dimensions(
            output.missing_dimensions + rag_result.reflection.missing_dimensions
        )
        has_minimum_signal = _has_minimum_company_analysis_signal(output, references)
        if has_minimum_signal and not filtered_missing_points:
            agent_action = "accept"
            agent_failure_type = "none"
        agent_decision = {
            "focus": "company core analysis with agentic RAG",
            "missing_points": filtered_missing_points,
            "bias_checks": _unique_strings(output.bias_checks + rag_result.reflection.bias_checks),
            "missing_dimensions": filtered_missing_dimensions,
            "failure_type": agent_failure_type,
            "recommended_action": agent_action,
            "revision_needed": (
                (output.revision_needed or rag_result.reflection.revision_needed)
                and agent_action != "accept"
            ),
        }
        logger.info(
            "Completed %s cached=%s references=%s agent_action=%s missing_dimensions=%s",
            self.name,
            not index_result.needs_reindex,
            len(references),
            agent_decision["recommended_action"],
            agent_decision["missing_dimensions"],
        )
        return {
            self.retrieval_state_key: {
                "company": self.company,
                "pdf_path": str(pdf_path),
                "index_dir": str(index_result.index_dir),
                "document_hash": index_result.document_hash,
                "embedding_model": self._vector_store_service.embedding_model_name,
                "index_ready": index_result.index_ready,
                "needs_reindex": index_result.needs_reindex,
                "top_k": retrieval_state["top_k"],
                "retrieval_queries": rag_result.retrieval_queries,
                "retrieved_chunks": normalized_chunks,
                "references": rag_result.references,
            },
            self.state_key: {
                "company": self.company,
                "agentic_rag_plan": rag_result.agentic_rag_plan,
                "evidence": output.evidence,
                "references": references,
                "core_competitiveness": output.core_competitiveness,
                "diversification_strategy": output.diversification_strategy,
                "agent_decision": agent_decision,
                "search_evaluation": state[self.state_key]["search_evaluation"],
                "reflection": state[self.state_key]["reflection"],
                "ready": True,
            }
        }

    def _collect_trusted_web_results(self, refined_query: str):
        queries = _build_company_web_queries(self.company, refined_query, self.state_key)
        collected = []
        seen_urls: set[str] = set()
        for query in queries:
            for item in self._web_search_service.search_trusted_company_results(self.company, query, max_results=8):
                if item.url in seen_urls:
                    continue
                collected.append(item)
                seen_urls.add(item.url)
        return collected[:6]


class LGESCorePortfolioAgent(CompanyCorePortfolioAgent):
    def __init__(
        self,
        config: AppConfig,
        llm_service: LLMService,
        rag_service: AgenticRAGService,
        web_search_service: WebSearchService,
        vector_store_service: CompanyVectorStoreService,
    ) -> None:
        super().__init__(
            config=config,
            llm_service=llm_service,
            rag_service=rag_service,
            web_search_service=web_search_service,
            vector_store_service=vector_store_service,
            name="lges_core_portfolio_agent",
            company="LG Energy Solution",
            state_key="lges_core_analysis",
            retrieval_state_key="lges_retrieval",
            company_id="lges",
        )


class CATLCorePortfolioAgent(CompanyCorePortfolioAgent):
    def __init__(
        self,
        config: AppConfig,
        llm_service: LLMService,
        rag_service: AgenticRAGService,
        web_search_service: WebSearchService,
        vector_store_service: CompanyVectorStoreService,
    ) -> None:
        super().__init__(
            config=config,
            llm_service=llm_service,
            rag_service=rag_service,
            web_search_service=web_search_service,
            vector_store_service=vector_store_service,
            name="catl_core_portfolio_agent",
            company="CATL",
            state_key="catl_core_analysis",
            retrieval_state_key="catl_retrieval",
            company_id="catl",
        )


def _build_company_web_queries(company: str, refined_query: str, state_key: str) -> list[str]:
    company_focus = company
    query_focus = refined_query.strip()
    base_queries = [
        f"{company_focus} battery technology roadmap Reuters official",
        f"{company_focus} battery manufacturing capacity expansion Reuters official",
        f"{company_focus} battery ESS diversification strategy Reuters official",
        f"{company_focus} battery portfolio diversification official site Reuters",
        f"{company_focus} battery risks headwinds delays Reuters official",
        f"{company_focus} battery pricing pressure utilization challenge Reuters official",
    ]
    if "lges" in state_key:
        base_queries.append(f"{company_focus} North America battery production official Reuters")
    if "catl" in state_key:
        base_queries.append(f"{company_focus} LFP battery strategy official Reuters")
    if query_focus:
        base_queries.append(f"{company_focus} {query_focus}")
    return list(dict.fromkeys(base_queries))


def _pick_stricter_action(left: str, right: str) -> str:
    return left if _DECISION_ACTION_PRIORITY.get(left, 0) >= _DECISION_ACTION_PRIORITY.get(right, 0) else right


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        unique.append(stripped)
        seen.add(stripped)
    return unique


def _filter_non_blocking_company_points(values: list[str]) -> list[str]:
    filtered: list[str] = []
    for value in _unique_strings(values):
        normalized = value.lower()
        if any(re.search(pattern, normalized) for pattern in _NON_BLOCKING_COMPANY_POINT_PATTERNS):
            continue
        filtered.append(value)
    return filtered
