from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict


def merge_unique_strings(existing: list[str], update: list[str] | None) -> list[str]:
    if not update:
        return list(existing)

    merged = list(existing)
    seen = set(existing)
    for item in update:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


WorkflowPhase = Literal[
    "init",
    "initial_parallel",
    "swot_parallel",
    "comparison",
    "reporting",
    "done",
    "failed",
]

SearchVerdict = Literal[
    "pending",
    "approved",
    "revise",
    "retrieve",
    "exhausted",
]

ReflectionAction = Literal["accept", "retry_rewrite", "retry_retrieve", "fail"]
ReflectionFailureType = Literal[
    "none",
    "insufficient_coverage",
    "redundant_evidence",
    "weak_grounding",
    "missing_numeric_support",
    "source_concentration",
    "format_issue",
]


class ReflectionState(TypedDict):
    focus: str
    missing_points: list[str]
    bias_checks: list[str]
    missing_dimensions: list[str]
    failure_type: ReflectionFailureType
    recommended_action: ReflectionAction
    revision_needed: bool


class AgentDecisionState(ReflectionState):
    pass


class SearchEvaluationState(TypedDict):
    verdict: SearchVerdict
    retry_count: int
    max_retry: int
    revision_count: int
    max_revision: int
    last_reason: str


class ControlState(TypedDict):
    current_node: str
    step_count: int
    max_step_count: int
    end_flag: bool
    fail_reason: str


class SupervisorState(TypedDict):
    refined_user_query: str
    workflow_phase: WorkflowPhase
    revision_requests: list[str]


class RetrievalChunkState(TypedDict):
    chunk_id: str
    page: int
    score: float
    content: str


class RetrievalState(TypedDict):
    company: str
    pdf_path: str
    index_dir: str
    document_hash: str
    embedding_model: str
    index_ready: bool
    needs_reindex: bool
    top_k: int
    retrieval_queries: list[str]
    retrieved_chunks: list[RetrievalChunkState]
    references: list[str]


class MarketAnalysisState(TypedDict):
    market_view: str
    evidence: list[str]
    references: list[str]
    agent_decision: AgentDecisionState
    search_evaluation: SearchEvaluationState
    reflection: ReflectionState
    ready: bool


class CompanyCoreAnalysisState(TypedDict):
    company: str
    agentic_rag_plan: list[str]
    evidence: list[str]
    references: list[str]
    core_competitiveness: list[str]
    diversification_strategy: list[str]
    agent_decision: AgentDecisionState
    search_evaluation: SearchEvaluationState
    reflection: ReflectionState
    ready: bool


class SWOTState(TypedDict):
    company: str
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    threats: list[str]
    references: list[str]
    ready: bool


class ComparisonState(TypedDict):
    strategic_differences: list[str]
    strengths_weaknesses_comparison: list[str]
    conclusion: str
    references: list[str]
    ready: bool


class ReportState(TypedDict):
    title: str
    summary: str
    markdown_body: str
    markdown_path: str
    pdf_path: str
    references: list[str]
    quality_check: dict[str, bool]
    agent_decision: AgentDecisionState
    search_evaluation: SearchEvaluationState
    reflection: ReflectionState
    ready: bool


class GraphState(TypedDict):
    raw_user_query: str
    control: ControlState
    supervisor: SupervisorState
    market_analysis: MarketAnalysisState
    lges_retrieval: RetrievalState
    catl_retrieval: RetrievalState
    lges_core_analysis: CompanyCoreAnalysisState
    catl_core_analysis: CompanyCoreAnalysisState
    lges_swot: SWOTState
    catl_swot: SWOTState
    comparison: ComparisonState
    report: ReportState
    collected_references: Annotated[list[str], merge_unique_strings]
    execution_trace: Annotated[list[str], operator.add]
