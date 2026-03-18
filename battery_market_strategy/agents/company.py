from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseAgent
from ..config import AppConfig
from ..execution_state import is_approved, update_search_evaluation
from ..reflection_utils import (
    assess_company_output,
    build_reflection,
    filter_company_missing_dimensions,
    reflection_action_to_verdict,
)
from ..reference_utils import sanitize_references
from ..schemas import CompanyAnalysisOutput
from ..state_models import GraphState
from ..services import AgenticRAGService, CompanyVectorStoreService, LLMService

logger = logging.getLogger(__name__)


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
        chunk_preview = "\n\n".join(
            f"[{chunk['reference']}] {chunk['content'][:900]}" for chunk in rag_result.retrieved_chunks[:10]
        )

        system_prompt = (
            "You are a corporate strategy analyst focused on battery companies. "
            "Use only the provided company-PDF evidence. Write all outputs in Korean. "
            "Prefer non-overlapping points grounded in different sections or pages when the evidence allows it. "
            "Avoid repeating the same plant, customer, product line, or chemistry claim across multiple bullets unless the repetition adds a distinct strategic implication. "
            "Favor explicit facts with named technologies, applications, geographies, production footprints, customer programs, or portfolio moves over generic praise. "
            "Separate what the company document states directly from what you cautiously infer. "
            "If a detail is not explicit in the company PDF, mark it as not clearly disclosed instead of treating it as a required blocker. "
            "Do not require competitor comparison, external market-share data, or financial metrics unless they are explicitly present in the supplied company PDF. "
            "Detailed customer names, service expansion, recycling strategy, or supply-chain specifics may be absent in a limited company PDF sample and should usually be treated as optional enrichment rather than hard blockers. "
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
            "모든 결론은 보수적으로 정리하고, 확인된 사실과 해석을 섞지 마.\n\n"
            f"회사 PDF 근거:\n{chunk_preview}"
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
        references = sanitize_references(rag_result.references)
        rule_reflection = assess_company_output(output, references)
        llm_failure_type = output.failure_type if output.failure_type != "none" else rag_result.reflection.failure_type
        llm_missing_dimensions = filter_company_missing_dimensions(
            output.missing_dimensions + rag_result.reflection.missing_dimensions
        )
        llm_missing_points = output.missing_points + rag_result.reflection.missing_points
        llm_bias_checks = output.bias_checks + rag_result.reflection.bias_checks
        llm_action = "accept"
        if rule_reflection["recommended_action"] != "accept":
            llm_action = (
                rag_result.reflection.recommended_action
                if rag_result.reflection.recommended_action != "accept"
                else output.recommended_action
            )
        else:
            llm_missing_points = []
            llm_missing_dimensions = []
        reflection = build_reflection(
            focus="company core analysis with agentic RAG",
            llm_missing_points=llm_missing_points,
            llm_bias_checks=llm_bias_checks,
            llm_missing_dimensions=llm_missing_dimensions,
            llm_failure_type=llm_failure_type,
            llm_action=llm_action,
            rule_missing_points=rule_reflection["missing_points"],
            rule_bias_checks=rule_reflection["bias_checks"],
            rule_missing_dimensions=rule_reflection["missing_dimensions"],
            rule_failure_type=rule_reflection["failure_type"],
            rule_action=rule_reflection["recommended_action"],
        )
        has_minimum_signal = _has_minimum_company_analysis_signal(output, references)
        if has_minimum_signal and reflection["recommended_action"] == "accept":
            verdict = "approved"
        else:
            verdict = reflection_action_to_verdict(reflection["recommended_action"])
        reason = "; ".join(reflection["missing_points"]) if reflection["missing_points"] else "reflection approved"
        search_evaluation = update_search_evaluation(
            state[self.state_key]["search_evaluation"],
            verdict=verdict,
            last_reason=reason,
        )
        logger.info(
            "Completed %s cached=%s references=%s verdict=%s action=%s missing_dimensions=%s retry_count=%s revision_count=%s reason=%s",
            self.name,
            not index_result.needs_reindex,
            len(references),
            search_evaluation["verdict"],
            reflection["recommended_action"],
            reflection["missing_dimensions"],
            search_evaluation["retry_count"],
            search_evaluation["revision_count"],
            search_evaluation["last_reason"],
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
                "search_evaluation": search_evaluation,
                "reflection": reflection,
                "ready": True,
            }
        }


class LGESCorePortfolioAgent(CompanyCorePortfolioAgent):
    def __init__(
        self,
        config: AppConfig,
        llm_service: LLMService,
        rag_service: AgenticRAGService,
        vector_store_service: CompanyVectorStoreService,
    ) -> None:
        super().__init__(
            config=config,
            llm_service=llm_service,
            rag_service=rag_service,
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
        vector_store_service: CompanyVectorStoreService,
    ) -> None:
        super().__init__(
            config=config,
            llm_service=llm_service,
            rag_service=rag_service,
            vector_store_service=vector_store_service,
            name="catl_core_portfolio_agent",
            company="CATL",
            state_key="catl_core_analysis",
            retrieval_state_key="catl_retrieval",
            company_id="catl",
        )
