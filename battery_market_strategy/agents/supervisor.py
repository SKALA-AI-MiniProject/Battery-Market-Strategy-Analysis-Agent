from __future__ import annotations

import logging

from .base import BaseAgent
from ..execution_state import is_exhausted, should_retry
from ..spec import FIXED_USER_PROMPT
from ..state_models import GraphState

logger = logging.getLogger(__name__)


class SupervisorAgent(BaseAgent):
    name = "supervisor_agent"

    def run(self, state: GraphState) -> dict:
        supervisor_state = state["supervisor"]
        effective_query = state["raw_user_query"].strip() or FIXED_USER_PROMPT

        initial_ready = all(
            [
                state["market_analysis"]["ready"],
                state["lges_core_analysis"]["ready"],
                state["catl_core_analysis"]["ready"],
            ]
        )
        initial_retry_requests = self._collect_retry_requests(
            [
                ("market_analysis", state["market_analysis"]["search_evaluation"]),
                ("lges_core_analysis", state["lges_core_analysis"]["search_evaluation"]),
                ("catl_core_analysis", state["catl_core_analysis"]["search_evaluation"]),
            ]
        )
        initial_exhausted = self._collect_exhausted_requests(
            [
                ("market_analysis", state["market_analysis"]["search_evaluation"]),
                ("lges_core_analysis", state["lges_core_analysis"]["search_evaluation"]),
                ("catl_core_analysis", state["catl_core_analysis"]["search_evaluation"]),
            ]
        )

        swot_ready = all([state["lges_swot"]["ready"], state["catl_swot"]["ready"]])
        comparison_ready = state["comparison"]["ready"]
        report_quality = state["report"]["quality_check"]
        report_ready = state["report"]["ready"]
        report_retry_requests = self._collect_retry_requests(
            [("report", state["report"]["search_evaluation"])]
        )
        report_exhausted = self._collect_exhausted_requests(
            [("report", state["report"]["search_evaluation"])]
        )
        report_quality_issues = self._collect_quality_issues(report_quality)
        logger.info(
            "Supervisor phase=%s initial_ready=%s initial_retry=%s initial_exhausted=%s swot_ready=%s comparison_ready=%s report_ready=%s report_retry=%s report_exhausted=%s report_quality_issues=%s",
            supervisor_state["workflow_phase"],
            initial_ready,
            initial_retry_requests,
            initial_exhausted,
            swot_ready,
            comparison_ready,
            report_ready,
            report_retry_requests,
            report_exhausted,
            report_quality_issues,
        )

        if supervisor_state["workflow_phase"] == "init":
            logger.info("Supervisor transition init -> initial_parallel")
            return {
                "supervisor": {
                    "refined_user_query": effective_query,
                    "workflow_phase": "initial_parallel",
                    "revision_requests": [],
                }
            }

        if supervisor_state["workflow_phase"] == "initial_parallel":
            if initial_exhausted:
                return self._fail(
                    state,
                    f"Initial analysis exhausted retries for: {', '.join(initial_exhausted)}",
                    initial_exhausted,
                )
            if not initial_ready or initial_retry_requests:
                logger.info("Supervisor staying in initial_parallel revision_requests=%s", initial_retry_requests)
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "initial_parallel",
                        "revision_requests": initial_retry_requests,
                    }
                }
            logger.info("Supervisor transition initial_parallel -> swot_parallel")
            return {
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "swot_parallel",
                    "revision_requests": [],
                }
            }

        if supervisor_state["workflow_phase"] == "swot_parallel":
            if not swot_ready:
                logger.info("Supervisor staying in swot_parallel waiting_for=%s", self._collect_pending_swot(state))
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "swot_parallel",
                        "revision_requests": [],
                    }
                }
            logger.info("Supervisor transition swot_parallel -> comparison")
            return {
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "comparison",
                    "revision_requests": [],
                }
            }

        if supervisor_state["workflow_phase"] == "comparison":
            if not comparison_ready:
                logger.info("Supervisor staying in comparison waiting_for=comparison")
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "comparison",
                        "revision_requests": [],
                    }
                }
            logger.info("Supervisor transition comparison -> reporting")
            return {
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "reporting",
                    "revision_requests": [],
                }
                }

        if supervisor_state["workflow_phase"] == "reporting":
            if report_exhausted:
                return self._fail(
                    state,
                    f"Report generation exhausted retries for: {', '.join(report_exhausted)}",
                    report_quality_issues or report_exhausted,
                )
            if report_quality_issues and not report_retry_requests:
                return self._fail(
                    state,
                    f"Report quality gate failed: {', '.join(report_quality_issues)}",
                    report_quality_issues,
                )
            if not report_ready or report_retry_requests:
                logger.info("Supervisor staying in reporting revision_requests=%s", report_retry_requests or report_quality_issues)
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "reporting",
                        "revision_requests": report_retry_requests or report_quality_issues,
                    }
                }
            logger.info("Supervisor transition reporting -> done")
            return {
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "done",
                    "revision_requests": report_quality_issues,
                }
            }

        return {"supervisor": supervisor_state}

    @staticmethod
    def _collect_retry_requests(checks: list[tuple[str, dict]]) -> list[str]:
        return [name for name, evaluation in checks if should_retry(evaluation)]

    @staticmethod
    def _collect_exhausted_requests(checks: list[tuple[str, dict]]) -> list[str]:
        return [name for name, evaluation in checks if is_exhausted(evaluation)]

    @staticmethod
    def _collect_quality_issues(quality_check: dict[str, bool]) -> list[str]:
        return [name for name, is_ok in quality_check.items() if not is_ok]

    @staticmethod
    def _fail(state: GraphState, reason: str, revision_requests: list[str]) -> dict:
        logger.error("Supervisor failing workflow reason=%s revision_requests=%s", reason, revision_requests)
        return {
            "supervisor": {
                **state["supervisor"],
                "refined_user_query": state["supervisor"]["refined_user_query"] or state["raw_user_query"] or FIXED_USER_PROMPT,
                "workflow_phase": "failed",
                "revision_requests": revision_requests,
            },
            "control": {
                **state["control"],
                "fail_reason": reason,
            },
        }

    @staticmethod
    def _collect_pending_swot(state: GraphState) -> list[str]:
        pending: list[str] = []
        if not state["lges_swot"]["ready"]:
            pending.append("lges_swot")
        if not state["catl_swot"]["ready"]:
            pending.append("catl_swot")
        return pending
