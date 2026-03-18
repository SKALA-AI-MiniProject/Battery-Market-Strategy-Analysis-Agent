from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class QueryPlanOutput(BaseModel):
    queries: list[str] = Field(default_factory=list)


class RetrievalReflectionOutput(BaseModel):
    follow_up_queries: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    bias_checks: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    failure_type: Literal[
        "none",
        "insufficient_coverage",
        "redundant_evidence",
        "weak_grounding",
        "missing_numeric_support",
        "source_concentration",
        "format_issue",
    ] = "none"
    recommended_action: Literal["accept", "retry_rewrite", "retry_retrieve", "fail"] = "accept"
    revision_needed: bool = False


class MarketAnalysisOutput(BaseModel):
    market_view: str
    evidence: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    bias_checks: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    failure_type: Literal[
        "none",
        "insufficient_coverage",
        "redundant_evidence",
        "weak_grounding",
        "missing_numeric_support",
        "source_concentration",
        "format_issue",
    ] = "none"
    recommended_action: Literal["accept", "retry_rewrite", "retry_retrieve", "fail"] = "accept"
    revision_needed: bool = False


class CompanyAnalysisOutput(BaseModel):
    core_competitiveness: list[str] = Field(default_factory=list)
    diversification_strategy: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    bias_checks: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    failure_type: Literal[
        "none",
        "insufficient_coverage",
        "redundant_evidence",
        "weak_grounding",
        "missing_numeric_support",
        "source_concentration",
        "format_issue",
    ] = "none"
    recommended_action: Literal["accept", "retry_rewrite", "retry_retrieve", "fail"] = "accept"
    revision_needed: bool = False


class SWOTOutput(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class ComparisonOutput(BaseModel):
    strategic_differences: list[str] = Field(default_factory=list)
    strengths_weaknesses_comparison: list[str] = Field(default_factory=list)
    conclusion: str
    references: list[str] = Field(default_factory=list)


class ReportOutput(BaseModel):
    title: str
    summary: str
    markdown_body: str
    references: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    bias_checks: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
    failure_type: Literal[
        "none",
        "insufficient_coverage",
        "redundant_evidence",
        "weak_grounding",
        "missing_numeric_support",
        "source_concentration",
        "format_issue",
    ] = "none"
    recommended_action: Literal["accept", "retry_rewrite", "retry_retrieve", "fail"] = "accept"
    revision_needed: bool = False


class PDFReadyMarkdownOutput(BaseModel):
    """Structured output for PDF conversion stage (explicit schema)."""

    markdown_body: str = Field(description="Normalized markdown body for PDF renderer input")
