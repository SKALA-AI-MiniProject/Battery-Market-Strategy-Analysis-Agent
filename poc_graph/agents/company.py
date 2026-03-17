from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseAgent
from ..config import AppConfig
from ..execution_state import is_approved, update_search_evaluation
from ..schemas import CompanyAnalysisOutput
from ..state_models import GraphState
from ..services import AgenticRAGService, CompanyVectorStoreService, LLMService

logger = logging.getLogger(__name__)


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

        index_result = self._vector_store_service.ensure_index(self.company_id, pdf_path, index_dir)
        rag_result = self._rag_service.run(self.company, refined_query, index_result.index_dir, retrieval_state["top_k"])
        chunk_preview = "\n\n".join(
            f"[{chunk['reference']}] {chunk['content'][:900]}" for chunk in rag_result.retrieved_chunks[:10]
        )

        system_prompt = (
            "You are a corporate strategy analyst focused on battery companies. "
            "Use only the provided company-PDF evidence. Write all outputs in Korean."
        )
        user_prompt = (
            f"회사: {self.company}\n"
            f"연구 목표: {refined_query}\n\n"
            "아래는 회사 PDF에서 회수한 근거다. 이 근거만 사용해 핵심 기술력과 포트폴리오 다각화 전략을 정리해.\n"
            "핵심 기술력은 기술 경쟁력, 생산/고객/지역 실행력, 제품 포트폴리오를 포함하고,\n"
            "다각화 전략은 EV 외 확장, chemistry diversification, ESS, 공급망/재활용/서비스 확장을 포함해.\n"
            "모든 결론은 보수적으로 정리하고, 확인된 사실과 해석을 섞지 마.\n\n"
            f"회사 PDF 근거:\n{chunk_preview}"
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
        references = sorted(set(output.references + rag_result.references))
        combined_missing_points = output.missing_points + rag_result.reflection.missing_points
        combined_bias_checks = output.bias_checks + rag_result.reflection.bias_checks
        if rag_result.reflection.revision_needed:
            verdict = "retrieve"
        elif output.revision_needed:
            verdict = "revise"
        else:
            verdict = "approved"
        reason = "; ".join(combined_missing_points) if combined_missing_points else "reflection approved"
        search_evaluation = update_search_evaluation(
            state[self.state_key]["search_evaluation"],
            verdict=verdict,
            last_reason=reason,
        )
        logger.info(
            "Completed %s cached=%s references=%s",
            self.name,
            not index_result.needs_reindex,
            len(references),
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
                "reflection": {
                    "focus": "company core analysis with agentic RAG",
                    "missing_points": combined_missing_points,
                    "bias_checks": combined_bias_checks,
                    "revision_needed": output.revision_needed or rag_result.reflection.revision_needed,
                },
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
