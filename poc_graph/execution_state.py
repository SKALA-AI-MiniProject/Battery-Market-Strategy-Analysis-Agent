from __future__ import annotations

from .state_models import SearchEvaluationState, SearchVerdict


def make_search_evaluation_state(max_retry: int, max_revision: int) -> SearchEvaluationState:
    return SearchEvaluationState(
        verdict="pending",
        retry_count=0,
        max_retry=max_retry,
        revision_count=0,
        max_revision=max_revision,
        last_reason="",
    )


def update_search_evaluation(
    previous: SearchEvaluationState,
    verdict: SearchVerdict,
    last_reason: str,
) -> SearchEvaluationState:
    retry_count = previous["retry_count"] + (1 if previous["verdict"] in {"revise", "retrieve"} else 0)
    revision_count = previous["revision_count"] + (1 if verdict in {"revise", "retrieve"} else 0)

    effective_verdict = verdict
    if verdict in {"revise", "retrieve"} and retry_count >= previous["max_retry"]:
        effective_verdict = "exhausted"

    return SearchEvaluationState(
        verdict=effective_verdict,
        retry_count=retry_count,
        max_retry=previous["max_retry"],
        revision_count=revision_count,
        max_revision=previous["max_revision"],
        last_reason=last_reason,
    )


def is_approved(evaluation: SearchEvaluationState) -> bool:
    return evaluation["verdict"] == "approved"


def should_retry(evaluation: SearchEvaluationState) -> bool:
    return evaluation["verdict"] in {"revise", "retrieve"} and evaluation["retry_count"] < evaluation["max_retry"]

