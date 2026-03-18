from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from .schemas import CompanyAnalysisOutput, MarketAnalysisOutput, ReportOutput, RetrievalReflectionOutput

ReflectionAction = Literal["accept", "retry_rewrite", "retry_retrieve", "fail"]
FailureType = Literal[
    "none",
    "insufficient_coverage",
    "redundant_evidence",
    "weak_grounding",
    "missing_numeric_support",
    "source_concentration",
    "format_issue",
]

_ACTION_PRIORITY: dict[ReflectionAction, int] = {
    "accept": 0,
    "retry_rewrite": 1,
    "retry_retrieve": 2,
    "fail": 3,
}

_MARKET_DIMENSIONS = {
    "EV 수요": ["ev", "electric vehicle", "전기차"],
    "ESS 수요": ["ess", "energy storage", "storage system", "에너지저장", "에너지 저장"],
    "정책/현지화": ["policy", "regulation", "ira", "tariff", "subsid", "localization", "현지화", "정책", "규제", "관세", "보조금"],
    "가격/수익성": ["price", "pricing", "margin", "profit", "asp", "가격", "수익성", "마진"],
    "공급/생산능력": ["capacity", "utilization", "oversupply", "expansion", "manufacturing", "공급", "생산능력", "캐파", "가동률", "증설", "과잉"],
    "리스크/역풍": ["risk", "headwind", "pressure", "volatility", "uncertainty", "리스크", "압박", "변동성", "둔화"],
}

_COMPANY_DIMENSIONS = {
    "기술/화학계": ["technology", "chemistry", "lfp", "ncm", "battery", "solid-state", "기술", "화학", "전고체", "리튬인산철", "하이니켈"],
    "생산거점/실행": ["plant", "factory", "capacity", "manufacturing", "production", "footprint", "공장", "생산", "증설", "북미", "유럽", "중국"],
    "고객/제품": ["customer", "oem", "product", "platform", "customer program", "고객", "제품", "플랫폼", "원통형", "파우치"],
    "ESS/비EV 확장": ["ess", "energy storage", "storage", "non-ev", "commercial", "grid", "에너지저장", "비ev", "ess"],
    "공급망/재활용/서비스": ["supply chain", "recycling", "service", "lifecycle", "raw material", "공급망", "재활용", "서비스", "원재료"],
}

_MARKET_REQUIRED_DIMENSIONS = {"EV 수요", "ESS 수요", "정책/현지화"}
_MARKET_SECONDARY_DIMENSIONS = {"가격/수익성", "공급/생산능력", "리스크/역풍"}

_COMPANY_CORE_DIMENSIONS = {"기술/화학계", "생산거점/실행", "고객/제품", "ESS/비EV 확장"}
_COMPANY_OPTIONAL_DIMENSIONS = {"공급망/재활용/서비스"}
_RISK_BALANCE_KEYWORDS = [
    "risk",
    "headwind",
    "pressure",
    "constraint",
    "limitation",
    "delay",
    "uncertain",
    "volatility",
    "oversupply",
    "margin",
    "cost",
    "dependence",
    "regulatory",
    "리스크",
    "역풍",
    "압박",
    "제약",
    "한계",
    "지연",
    "불확실",
    "변동성",
    "과잉",
    "마진",
    "비용",
    "의존",
    "규제",
]


def build_reflection(
    *,
    focus: str,
    llm_missing_points: list[str],
    llm_bias_checks: list[str],
    llm_missing_dimensions: list[str],
    llm_failure_type: str,
    llm_action: str,
    rule_missing_points: list[str],
    rule_bias_checks: list[str],
    rule_missing_dimensions: list[str],
    rule_failure_type: FailureType,
    rule_action: ReflectionAction,
) -> dict:
    missing_points = _unique_strings(llm_missing_points + rule_missing_points)
    bias_checks = _unique_strings(llm_bias_checks + rule_bias_checks)
    missing_dimensions = _unique_strings(llm_missing_dimensions + rule_missing_dimensions)
    action = _pick_action(_coerce_action(llm_action), rule_action)
    failure_type = rule_failure_type if rule_failure_type != "none" else _coerce_failure_type(llm_failure_type)
    if action == "accept" and (missing_points or missing_dimensions):
        action = "retry_rewrite"
    return {
        "focus": focus,
        "missing_points": missing_points,
        "bias_checks": bias_checks,
        "missing_dimensions": missing_dimensions,
        "failure_type": failure_type,
        "recommended_action": action,
        "revision_needed": action != "accept",
    }


def assess_market_output(
    output: MarketAnalysisOutput,
    references: list[str],
) -> dict:
    combined_text = " ".join([output.market_view] + output.evidence).lower()
    missing_dimensions = [
        label for label, keywords in _MARKET_DIMENSIONS.items() if not any(keyword in combined_text for keyword in keywords)
    ]
    covered_dimensions = [label for label in _MARKET_DIMENSIONS if label not in missing_dimensions]
    blocking_missing_dimensions = [label for label in missing_dimensions if label in _MARKET_REQUIRED_DIMENSIONS]
    secondary_missing_dimensions = [label for label in missing_dimensions if label in _MARKET_SECONDARY_DIMENSIONS]
    unique_evidence_count = len({_normalize_text(item) for item in output.evidence if item.strip()})
    duplicate_bias = unique_evidence_count < len([item for item in output.evidence if item.strip()])
    source_domains = {
        urlparse(reference).netloc.lower()
        for reference in references
        if reference.startswith(("http://", "https://"))
    }
    has_numeric_support = bool(re.search(r"\d", combined_text))

    missing_points: list[str] = []
    bias_checks: list[str] = []
    failure_type: FailureType = "none"
    action: ReflectionAction = "accept"

    if len(output.evidence) < 5:
        missing_points.append("시장 분석 evidence 수가 부족함")
        failure_type = "weak_grounding"
        action = "retry_retrieve"
    if len(source_domains) < 3:
        missing_points.append("서로 다른 웹 출처 수가 부족함")
        failure_type = "source_concentration"
        action = "retry_retrieve"
    if blocking_missing_dimensions:
        missing_points.append("시장 분석 필수 축 일부가 비어 있음")
        failure_type = "insufficient_coverage"
        action = "retry_retrieve"
    elif len(covered_dimensions) < 4:
        missing_points.append("시장 분석 커버리지가 최소 수준에 못 미침")
        failure_type = "insufficient_coverage"
        action = "retry_retrieve"
    elif len(secondary_missing_dimensions) >= 2:
        bias_checks.append("시장 분석의 일부 보조 축은 충분히 다뤄지지 않음")
    if not has_numeric_support:
        bias_checks.append("숫자·날짜·정량 신호가 부족함")
        if action == "accept":
            failure_type = "missing_numeric_support"
            action = "retry_rewrite"
    if not any(keyword in combined_text for keyword in _RISK_BALANCE_KEYWORDS):
        bias_checks.append("시장 분석이 성장 요인 중심으로 기울었을 가능성이 있어 하방 요인 균형 점검이 필요함")
        if action == "accept":
            failure_type = "weak_grounding"
            action = "retry_rewrite"
    if duplicate_bias:
        bias_checks.append("evidence 간 중복 또는 재진술 가능성이 있음")
        if action == "accept":
            failure_type = "redundant_evidence"
            action = "retry_rewrite"

    return {
        "missing_points": missing_points,
        "bias_checks": bias_checks,
        "missing_dimensions": blocking_missing_dimensions,
        "failure_type": failure_type,
        "recommended_action": action,
    }


def assess_company_output(
    output: CompanyAnalysisOutput,
    references: list[str],
) -> dict:
    combined_text = " ".join(output.core_competitiveness + output.diversification_strategy + output.evidence).lower()
    missing_dimensions = [
        label for label, keywords in _COMPANY_DIMENSIONS.items() if not any(keyword in combined_text for keyword in keywords)
    ]
    covered_dimensions = [label for label in _COMPANY_DIMENSIONS if label not in missing_dimensions]
    core_covered_dimensions = [label for label in covered_dimensions if label in _COMPANY_CORE_DIMENSIONS]
    blocking_missing_dimensions = [
        label
        for label in missing_dimensions
        if label in _COMPANY_CORE_DIMENSIONS
    ]
    pages = {
        int(match.group(1))
        for reference in references
        if (match := re.match(r"^p\.(\d+)::", reference.strip()))
    }
    bullet_count = len(output.core_competitiveness) + len(output.diversification_strategy)
    unique_bullets = len(
        {
            _normalize_text(item)
            for item in output.core_competitiveness + output.diversification_strategy
            if item.strip()
        }
    )
    duplicate_bias = unique_bullets < bullet_count

    missing_points: list[str] = []
    bias_checks: list[str] = []
    failure_type: FailureType = "none"
    action: ReflectionAction = "accept"

    if len(output.core_competitiveness) < 2 or len(output.diversification_strategy) < 2 or len(output.evidence) < 3:
        missing_points.append("기업 분석의 핵심 포인트 또는 evidence 수가 부족함")
        failure_type = "weak_grounding"
        action = "retry_retrieve"
    if len(pages) < 2:
        missing_points.append("근거 페이지 다양성이 부족함")
        failure_type = "insufficient_coverage"
        action = "retry_retrieve"
    if len(core_covered_dimensions) < 2:
        missing_points.append("기업 분석이 핵심 축 두 개 이상을 충분히 다루지 못함")
        failure_type = "insufficient_coverage"
        action = "retry_retrieve"
    elif len(blocking_missing_dimensions) >= 3:
        missing_points.append("기업 분석이 핵심 축에 과도하게 치우쳐 있음")
        failure_type = "insufficient_coverage"
        action = "retry_retrieve"
    if any(label in missing_dimensions for label in _COMPANY_OPTIONAL_DIMENSIONS):
        bias_checks.append("공급망·재활용·서비스 확장 정보는 제한적일 수 있음")
    if not any(keyword in combined_text for keyword in _RISK_BALANCE_KEYWORDS):
        bias_checks.append("기업 분석이 강점·확장 서술에 치우쳤을 가능성이 있어 제약·리스크 균형 점검이 필요함")
        if action == "accept":
            failure_type = "weak_grounding"
            action = "retry_rewrite"
    if duplicate_bias:
        bias_checks.append("핵심 경쟁력 또는 다각화 포인트가 서로 중복될 가능성이 있음")
        if action == "accept":
            failure_type = "redundant_evidence"
            action = "retry_rewrite"

    return {
        "missing_points": missing_points,
        "bias_checks": bias_checks,
        "missing_dimensions": blocking_missing_dimensions,
        "failure_type": failure_type,
        "recommended_action": action,
    }


def assess_report_output(
    output: ReportOutput,
    markdown_body: str,
    references: list[str],
    quality_check: dict[str, bool],
) -> dict:
    missing_points: list[str] = []
    bias_checks: list[str] = []
    missing_dimensions: list[str] = []
    failure_type: FailureType = "none"
    action: ReflectionAction = "accept"

    required_sections = [
        "## Executive Summary",
        "## Market Analysis",
        "## LG Energy Solution",
        "## CATL",
        "## SWOT Comparison",
        "## Strategic Conclusion",
    ]
    absent_sections = [section for section in required_sections if section not in markdown_body]
    if absent_sections:
        missing_points.append("보고서 필수 섹션 일부가 없음")
        missing_dimensions.extend(absent_sections)
        failure_type = "format_issue"
        action = "retry_rewrite"
    if not references:
        missing_points.append("보고서 참고문헌이 비어 있음")
        failure_type = "weak_grounding"
        action = "retry_rewrite"
    if not all(quality_check.values()):
        bias_checks.extend([name for name, passed in quality_check.items() if not passed])
        if action == "accept":
            failure_type = "format_issue"
            action = "retry_rewrite"

    return {
        "missing_points": missing_points,
        "bias_checks": bias_checks,
        "missing_dimensions": missing_dimensions,
        "failure_type": failure_type,
        "recommended_action": action,
    }


def reflection_action_to_verdict(action: str) -> str:
    if action == "retry_retrieve":
        return "retrieve"
    if action in {"retry_rewrite", "fail"}:
        return "revise"
    return "approved"


def merge_retrieval_reflection(
    reflection: RetrievalReflectionOutput,
    *,
    rule_missing_points: list[str],
    rule_bias_checks: list[str],
    rule_missing_dimensions: list[str],
    rule_failure_type: FailureType,
    rule_action: ReflectionAction,
) -> RetrievalReflectionOutput:
    merged = build_reflection(
        focus="company retrieval sufficiency check",
        llm_missing_points=reflection.missing_points,
        llm_bias_checks=reflection.bias_checks,
        llm_missing_dimensions=reflection.missing_dimensions,
        llm_failure_type=reflection.failure_type,
        llm_action=reflection.recommended_action,
        rule_missing_points=rule_missing_points,
        rule_bias_checks=rule_bias_checks,
        rule_missing_dimensions=rule_missing_dimensions,
        rule_failure_type=rule_failure_type,
        rule_action=rule_action,
    )
    return RetrievalReflectionOutput(
        follow_up_queries=reflection.follow_up_queries,
        missing_points=merged["missing_points"],
        bias_checks=merged["bias_checks"],
        missing_dimensions=merged["missing_dimensions"],
        failure_type=merged["failure_type"],
        recommended_action=merged["recommended_action"],
        revision_needed=merged["revision_needed"],
    )


def filter_market_missing_dimensions(values: list[str]) -> list[str]:
    return [value for value in _unique_strings(values) if value in _MARKET_DIMENSIONS]


def filter_company_missing_dimensions(values: list[str]) -> list[str]:
    return [value for value in _unique_strings(values) if value in _COMPANY_DIMENSIONS]


def _coerce_action(value: str) -> ReflectionAction:
    if value in _ACTION_PRIORITY:
        return value  # type: ignore[return-value]
    return "accept"


def _coerce_failure_type(value: str) -> FailureType:
    if value in {
        "none",
        "insufficient_coverage",
        "redundant_evidence",
        "weak_grounding",
        "missing_numeric_support",
        "source_concentration",
        "format_issue",
    }:
        return value  # type: ignore[return-value]
    return "none"


def _pick_action(left: ReflectionAction, right: ReflectionAction) -> ReflectionAction:
    return left if _ACTION_PRIORITY[left] >= _ACTION_PRIORITY[right] else right


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        unique.append(stripped)
        seen.add(stripped)
    return unique
