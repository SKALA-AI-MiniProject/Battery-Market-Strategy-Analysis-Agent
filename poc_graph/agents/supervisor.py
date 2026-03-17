from __future__ import annotations

from .base import BaseAgent
from ..execution_state import should_retry
from ..spec import FIXED_USER_PROMPT
from ..state_models import GraphState


class SupervisorAgent(BaseAgent):
    name = "supervisor_agent"
    refined_user_query = FIXED_USER_PROMPT

    def run(self, state: GraphState) -> dict:
        supervisor_state = state["supervisor"]

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

        swot_ready = all([state["lges_swot"]["ready"], state["catl_swot"]["ready"]])
        comparison_ready = state["comparison"]["ready"]
        report_quality = state["report"]["quality_check"]
        report_ready = state["report"]["ready"]
        report_retry_requests = self._collect_retry_requests(
            [("report", state["report"]["search_evaluation"])]
        )
        report_quality_issues = self._collect_quality_issues(report_quality)

        if supervisor_state["workflow_phase"] == "init":
            return {
                "supervisor": {
                    "refined_user_query": self.refined_user_query,
                    "workflow_phase": "initial_parallel",
                    "revision_requests": [],
                }
            }

        if supervisor_state["workflow_phase"] == "initial_parallel":
            if not initial_ready or initial_retry_requests:
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "initial_parallel",
                        "revision_requests": initial_retry_requests,
                    }
                }
            return {
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "swot_parallel",
                    "revision_requests": [],
                }
            }

        if supervisor_state["workflow_phase"] == "swot_parallel":
            if not swot_ready:
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "swot_parallel",
                        "revision_requests": [],
                    }
                }
            return {
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "comparison",
                    "revision_requests": [],
                }
            }

        if supervisor_state["workflow_phase"] == "comparison":
            if not comparison_ready:
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "comparison",
                        "revision_requests": [],
                    }
                }
            return {
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "reporting",
                    "revision_requests": [],
                }
            }

        if supervisor_state["workflow_phase"] == "reporting":
            if not report_ready or report_retry_requests:
                return {
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "reporting",
                        "revision_requests": report_retry_requests or report_quality_issues,
                    }
                }
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
    def _collect_quality_issues(quality_check: dict[str, bool]) -> list[str]:
        return [name for name, is_ok in quality_check.items() if not is_ok]
