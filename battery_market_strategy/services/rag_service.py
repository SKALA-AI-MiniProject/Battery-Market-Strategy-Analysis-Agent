from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document

from ..schemas import QueryPlanOutput, RetrievalReflectionOutput
from .llm_service import LLMService
from .vector_store_service import CompanyVectorStoreService
from .web_search_service import WebSearchService

logger = logging.getLogger(__name__)


@dataclass
class RAGRunResult:
    agentic_rag_plan: list[str]
    retrieval_queries: list[str]
    retrieved_chunks: list[dict]
    references: list[str]
    reflection: RetrievalReflectionOutput


class AgenticRAGService:
    def __init__(
        self,
        llm_service: LLMService,
        vector_store_service: CompanyVectorStoreService,
        web_search_service: WebSearchService,
        max_rounds: int,
    ) -> None:
        self._llm_service = llm_service
        self._vector_store_service = vector_store_service
        self._web_search_service = web_search_service
        self._max_rounds = max_rounds

    def run(self, company: str, refined_query: str, index_dir: Path, top_k: int) -> RAGRunResult:
        logger.info("Starting agentic RAG company=%s", company)
        plan = self._plan_queries(company, refined_query)
        all_queries = list(plan.queries)
        all_chunks: list[dict] = []
        reflection = RetrievalReflectionOutput()

        for round_index in range(self._max_rounds):
            current_queries = all_queries if round_index == 0 else reflection.follow_up_queries
            if not current_queries:
                break
            logger.info("RAG round=%s company=%s query_count=%s", round_index + 1, company, len(current_queries))
            for query in current_queries:
                retrieved = self._vector_store_service.retrieve(index_dir, query, top_k)
                all_chunks.extend(self._normalize_chunks(retrieved))

            deduped = self._dedupe_chunks(all_chunks)
            reflection = self._reflect(company, refined_query, deduped)
            all_chunks = deduped
            if not reflection.revision_needed:
                logger.info("RAG reflection approved company=%s after round=%s", company, round_index + 1)
                break
            for query in reflection.follow_up_queries:
                if query not in all_queries:
                    all_queries.append(query)
        else:
            reflection = self._reflect(company, refined_query, self._dedupe_chunks(all_chunks))

        all_chunks = self._dedupe_chunks(all_chunks)
        references = sorted({chunk["reference"] for chunk in all_chunks})
        logger.info("Completed agentic RAG company=%s chunks=%s", company, len(all_chunks))
        return RAGRunResult(
            agentic_rag_plan=plan.queries,
            retrieval_queries=all_queries,
            retrieved_chunks=all_chunks,
            references=references,
            reflection=reflection,
        )

    def _plan_queries(self, company: str, refined_query: str) -> QueryPlanOutput:
        system_prompt = (
            "You are designing retrieval queries for a company-specific Agentic RAG workflow. "
            "Return concise search queries tailored to the named company's own PDF corpus only. "
            "Do not mention other companies, comparisons, or information outside that single company's document."
        )
        user_prompt = (
            f"Company: {company}\n"
            f"Research objective: {refined_query}\n"
            "Return 4 queries for this company only. Cover: core competitiveness, diversification, risk/counter-evidence, and execution evidence. "
            "The query text must mention only the named company."
        )
        return self._llm_service.invoke_structured(system_prompt, user_prompt, QueryPlanOutput)

    def _reflect(self, company: str, refined_query: str, chunks: list[dict]) -> RetrievalReflectionOutput:
        system_prompt = (
            "You are auditing the sufficiency of retrieved evidence for company analysis. "
            "Ask for follow-up queries only if the retrieved context is insufficient to support a basic company-only analysis. "
            "Treat unavailable details as acceptable limitations if the current evidence already supports at least a minimal summary of core competitiveness and diversification. "
            "Do not ask for competitor comparison, external market-share data, financial metrics, or information that is not likely to exist in the named company's own PDF. "
            "Follow-up queries must target only the named company's own PDF."
        )
        chunk_preview = "\n\n".join(
            f"[{item['reference']}] {item['content'][:700]}" for item in chunks[:8]
        )
        web_counter_evidence = self._web_search_service.search(
            f"{company} battery diversification risks headwinds counter evidence", max_results=3
        )
        user_prompt = (
            f"Company: {company}\n"
            f"Research objective: {refined_query}\n\n"
            f"Retrieved company-PDF evidence:\n{chunk_preview}\n\n"
            f"Optional external counter-evidence snippets:\n{chr(10).join(web_counter_evidence)}\n\n"
            "Approve the evidence if it is sufficient to produce at least 2 concrete points on core competitiveness, 2 on diversification, and 3 grounded evidence bullets. "
            "If evidence is insufficient, provide focused follow-up retrieval queries for the company PDF only. "
            "Do not request information about any other company or unavailable external benchmarking data."
        )
        return self._llm_service.invoke_structured(system_prompt, user_prompt, RetrievalReflectionOutput)

    @staticmethod
    def _normalize_chunks(results: list[tuple[Document, float]]) -> list[dict]:
        normalized = []
        for doc, score in results:
            page = int(doc.metadata.get("page", 0)) + 1
            chunk_id = str(doc.metadata.get("chunk_id", "unknown"))
            reference = f"p.{page}::{chunk_id}"
            normalized.append(
                {
                    "chunk_id": chunk_id,
                    "page": page,
                    "score": float(score),
                    "content": doc.page_content,
                    "reference": reference,
                }
            )
        return normalized

    @staticmethod
    def _dedupe_chunks(chunks: list[dict]) -> list[dict]:
        deduped: dict[str, dict] = {}
        for chunk in chunks:
            deduped[chunk["chunk_id"]] = chunk
        return list(deduped.values())
