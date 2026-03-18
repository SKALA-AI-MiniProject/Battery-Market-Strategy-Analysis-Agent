from __future__ import annotations

from .config import AppConfig
from .execution_state import make_search_evaluation_state
from .spec import (
    INITIAL_SEARCH_MAX_RETRY,
    INITIAL_SEARCH_MAX_REVISION,
    MAX_STEP_COUNT,
    REPORT_MAX_RETRY,
    REPORT_MAX_REVISION,
)
from .state_models import (
    AgentDecisionState,
    ControlState,
    CompanyCoreAnalysisState,
    ComparisonState,
    GraphState,
    MarketAnalysisState,
    ReflectionState,
    ReportState,
    RetrievalState,
    SWOTState,
    SupervisorState,
)


def make_reflection_state(focus: str) -> ReflectionState:
    return ReflectionState(
        focus=focus,
        missing_points=[],
        bias_checks=[],
        missing_dimensions=[],
        failure_type="none",
        recommended_action="accept",
        revision_needed=False,
    )


def make_agent_decision_state(focus: str) -> AgentDecisionState:
    return AgentDecisionState(
        focus=focus,
        missing_points=[],
        bias_checks=[],
        missing_dimensions=[],
        failure_type="none",
        recommended_action="accept",
        revision_needed=False,
    )


def make_retrieval_state(company: str, pdf_path: str, index_dir: str, embedding_model: str, top_k: int) -> RetrievalState:
    return RetrievalState(
        company=company,
        pdf_path=pdf_path,
        index_dir=index_dir,
        document_hash="",
        embedding_model=embedding_model,
        index_ready=False,
        needs_reindex=False,
        top_k=top_k,
        retrieval_queries=[],
        retrieved_chunks=[],
        references=[],
    )


def make_initial_state(raw_user_query: str, config: AppConfig) -> GraphState:
    return GraphState(
        raw_user_query=raw_user_query,
        control=ControlState(
            current_node="init",
            step_count=0,
            max_step_count=MAX_STEP_COUNT,
            end_flag=False,
            fail_reason="",
        ),
        supervisor=SupervisorState(
            refined_user_query="",
            workflow_phase="init",
            revision_requests=[],
        ),
        market_analysis=MarketAnalysisState(
            market_view="",
            evidence=[],
            references=[],
            agent_decision=make_agent_decision_state("market attractiveness and sector structure"),
            search_evaluation=make_search_evaluation_state(
                max_retry=INITIAL_SEARCH_MAX_RETRY,
                max_revision=INITIAL_SEARCH_MAX_REVISION,
            ),
            reflection=make_reflection_state("market attractiveness and sector structure"),
            ready=False,
        ),
        lges_retrieval=make_retrieval_state(
            company="LG Energy Solution",
            pdf_path=str(config.lges_pdf_path),
            index_dir=str(config.lges_index_dir),
            embedding_model=config.embedding_model,
            top_k=config.top_k,
        ),
        catl_retrieval=make_retrieval_state(
            company="CATL",
            pdf_path=str(config.catl_pdf_path),
            index_dir=str(config.catl_index_dir),
            embedding_model=config.embedding_model,
            top_k=config.top_k,
        ),
        lges_core_analysis=CompanyCoreAnalysisState(
            company="LG Energy Solution",
            agentic_rag_plan=[],
            evidence=[],
            references=[],
            core_competitiveness=[],
            diversification_strategy=[],
            agent_decision=make_agent_decision_state("company core analysis with agentic RAG"),
            search_evaluation=make_search_evaluation_state(
                max_retry=INITIAL_SEARCH_MAX_RETRY,
                max_revision=INITIAL_SEARCH_MAX_REVISION,
            ),
            reflection=make_reflection_state("company core analysis with agentic RAG"),
            ready=False,
        ),
        catl_core_analysis=CompanyCoreAnalysisState(
            company="CATL",
            agentic_rag_plan=[],
            evidence=[],
            references=[],
            core_competitiveness=[],
            diversification_strategy=[],
            agent_decision=make_agent_decision_state("company core analysis with agentic RAG"),
            search_evaluation=make_search_evaluation_state(
                max_retry=INITIAL_SEARCH_MAX_RETRY,
                max_revision=INITIAL_SEARCH_MAX_REVISION,
            ),
            reflection=make_reflection_state("company core analysis with agentic RAG"),
            ready=False,
        ),
        lges_swot=SWOTState(
            company="LG Energy Solution",
            strengths=[],
            weaknesses=[],
            opportunities=[],
            threats=[],
            references=[],
            ready=False,
        ),
        catl_swot=SWOTState(
            company="CATL",
            strengths=[],
            weaknesses=[],
            opportunities=[],
            threats=[],
            references=[],
            ready=False,
        ),
        comparison=ComparisonState(
            strategic_differences=[],
            strengths_weaknesses_comparison=[],
            conclusion="",
            references=[],
            ready=False,
        ),
        report=ReportState(
            title="",
            summary="",
            markdown_body="",
            markdown_path="",
            pdf_path="",
            references=[],
            quality_check={
                "has_summary": False,
                "has_references": False,
                "summary_is_consistent": False,
                "references_are_relevant": False,
            },
            agent_decision=make_agent_decision_state("report quality check before PDF generation"),
            search_evaluation=make_search_evaluation_state(
                max_retry=REPORT_MAX_RETRY,
                max_revision=REPORT_MAX_REVISION,
            ),
            reflection=make_reflection_state("report quality check before PDF generation"),
            ready=False,
        ),
        collected_references=[],
        execution_trace=[],
    )
