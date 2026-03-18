from __future__ import annotations

import logging

from .base import BaseAgent
from ..execution_state import is_exhausted, should_retry, update_search_evaluation
from ..reflection_utils import (
    assess_company_output,
    assess_market_output,
    assess_report_output,
    build_reflection,
    filter_company_missing_dimensions,
    filter_market_missing_dimensions,
    reflection_action_to_verdict,
)
from ..schemas import CompanyAnalysisOutput, MarketAnalysisOutput, ReportOutput
from ..spec import FIXED_USER_PROMPT
from ..state_models import GraphState

logger = logging.getLogger(__name__)


class SupervisorAgent(BaseAgent):
    name = "supervisor_agent"

    def run(self, state: GraphState) -> dict:
        supervisor_state = state["supervisor"]
        effective_query = state["raw_user_query"].strip() or FIXED_USER_PROMPT
        state_updates: dict = {}

        if supervisor_state["workflow_phase"] == "initial_parallel":
            state_updates.update(self._reflect_initial_phase(state))
        elif supervisor_state["workflow_phase"] == "reporting":
            state_updates.update(self._reflect_report_phase(state))

        effective_state = self._apply_updates(state, state_updates)

        initial_ready = all(
            [
                effective_state["market_analysis"]["ready"],
                effective_state["lges_core_analysis"]["ready"],
                effective_state["catl_core_analysis"]["ready"],
            ]
        )
        initial_retry_requests = self._collect_retry_requests(
            [
                ("market_analysis", effective_state["market_analysis"]["search_evaluation"]),
                ("lges_core_analysis", effective_state["lges_core_analysis"]["search_evaluation"]),
                ("catl_core_analysis", effective_state["catl_core_analysis"]["search_evaluation"]),
            ]
        )
        initial_exhausted = self._collect_exhausted_requests(
            [
                ("market_analysis", effective_state["market_analysis"]["search_evaluation"]),
                ("lges_core_analysis", effective_state["lges_core_analysis"]["search_evaluation"]),
                ("catl_core_analysis", effective_state["catl_core_analysis"]["search_evaluation"]),
            ]
        )

        swot_ready = all([effective_state["lges_swot"]["ready"], effective_state["catl_swot"]["ready"]])
        comparison_ready = effective_state["comparison"]["ready"]
        report_quality = effective_state["report"]["quality_check"]
        report_ready = effective_state["report"]["ready"]
        report_retry_requests = self._collect_retry_requests(
            [("report", effective_state["report"]["search_evaluation"])]
        )
        report_exhausted = self._collect_exhausted_requests(
            [("report", effective_state["report"]["search_evaluation"])]
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
                **state_updates,
                "supervisor": {
                    "refined_user_query": effective_query,
                    "workflow_phase": "initial_parallel",
                    "revision_requests": [],
                },
            }

        if supervisor_state["workflow_phase"] == "initial_parallel":
            if initial_exhausted:
                failure = self._fail(
                    effective_state,
                    f"Initial analysis exhausted retries for: {', '.join(initial_exhausted)}",
                    initial_exhausted,
                )
                return {**state_updates, **failure}
            if not initial_ready or initial_retry_requests:
                logger.info("Supervisor staying in initial_parallel revision_requests=%s", initial_retry_requests)
                return {
                    **state_updates,
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "initial_parallel",
                        "revision_requests": initial_retry_requests,
                    },
                }
            logger.info("Supervisor transition initial_parallel -> swot_parallel")
            return {
                **state_updates,
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "swot_parallel",
                    "revision_requests": [],
                },
            }

        if supervisor_state["workflow_phase"] == "swot_parallel":
            if not swot_ready:
                logger.info(
                    "Supervisor staying in swot_parallel waiting_for=%s",
                    self._collect_pending_swot(effective_state),
                )
                return {
                    **state_updates,
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "swot_parallel",
                        "revision_requests": [],
                    },
                }
            logger.info("Supervisor transition swot_parallel -> comparison")
            return {
                **state_updates,
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "comparison",
                    "revision_requests": [],
                },
            }

        if supervisor_state["workflow_phase"] == "comparison":
            if not comparison_ready:
                logger.info("Supervisor staying in comparison waiting_for=comparison")
                return {
                    **state_updates,
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "comparison",
                        "revision_requests": [],
                    },
                }
            logger.info("Supervisor transition comparison -> reporting")
            return {
                **state_updates,
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "reporting",
                    "revision_requests": [],
                },
            }

        if supervisor_state["workflow_phase"] == "reporting":
            if report_exhausted:
                failure = self._fail(
                    effective_state,
                    f"Report generation exhausted retries for: {', '.join(report_exhausted)}",
                    report_quality_issues or report_exhausted,
                )
                return {**state_updates, **failure}
            if report_quality_issues and not report_retry_requests:
                failure = self._fail(
                    effective_state,
                    f"Report quality gate failed: {', '.join(report_quality_issues)}",
                    report_quality_issues,
                )
                return {**state_updates, **failure}
            if not report_ready or report_retry_requests:
                logger.info(
                    "Supervisor staying in reporting revision_requests=%s",
                    report_retry_requests or report_quality_issues,
                )
                return {
                    **state_updates,
                    "supervisor": {
                        **supervisor_state,
                        "workflow_phase": "reporting",
                        "revision_requests": report_retry_requests or report_quality_issues,
                    },
                }
            logger.info("Supervisor transition reporting -> done")
            return {
                **state_updates,
                "supervisor": {
                    **supervisor_state,
                    "workflow_phase": "done",
                    "revision_requests": report_quality_issues,
                },
            }

        return {**state_updates, "supervisor": supervisor_state}

    def _reflect_initial_phase(self, state: GraphState) -> dict:
        updates: dict = {}
        market_update = self._reflect_market_analysis(state)
        if market_update:
            updates["market_analysis"] = market_update

        lges_update = self._reflect_company_analysis(state, "lges_core_analysis")
        if lges_update:
            updates["lges_core_analysis"] = lges_update

        catl_update = self._reflect_company_analysis(state, "catl_core_analysis")
        if catl_update:
            updates["catl_core_analysis"] = catl_update

        return updates

    def _reflect_market_analysis(self, state: GraphState) -> dict | None:
        market_state = state["market_analysis"]
        if not market_state["ready"]:
            return None

        agent_decision = market_state["agent_decision"]
        output = MarketAnalysisOutput(
            market_view=market_state["market_view"],
            evidence=market_state["evidence"],
            references=market_state["references"],
            missing_points=agent_decision["missing_points"],
            bias_checks=agent_decision["bias_checks"],
            missing_dimensions=agent_decision["missing_dimensions"],
            failure_type=agent_decision["failure_type"],
            recommended_action=agent_decision["recommended_action"],
            revision_needed=agent_decision["revision_needed"],
        )
        rule_reflection = assess_market_output(output, market_state["references"])
        llm_missing_dimensions = filter_market_missing_dimensions(agent_decision["missing_dimensions"])
        llm_action = agent_decision["recommended_action"]
        llm_missing_points = agent_decision["missing_points"]
        has_minimum_signal = self._has_minimum_market_signal(market_state["market_view"], market_state["evidence"], market_state["references"])
        if has_minimum_signal and rule_reflection["recommended_action"] == "accept":
            llm_action = "accept"
            llm_missing_points = []
            llm_missing_dimensions = []

        reflection = build_reflection(
            focus="market attractiveness and sector structure",
            llm_missing_points=llm_missing_points,
            llm_bias_checks=agent_decision["bias_checks"],
            llm_missing_dimensions=llm_missing_dimensions,
            llm_failure_type=agent_decision["failure_type"],
            llm_action=llm_action,
            rule_missing_points=rule_reflection["missing_points"],
            rule_bias_checks=rule_reflection["bias_checks"],
            rule_missing_dimensions=rule_reflection["missing_dimensions"],
            rule_failure_type=rule_reflection["failure_type"],
            rule_action=rule_reflection["recommended_action"],
        )
        if has_minimum_signal and not reflection["missing_points"] and not reflection["missing_dimensions"]:
            reflection = {
                **reflection,
                "failure_type": "none",
                "recommended_action": "accept",
                "revision_needed": False,
            }
        reason = "; ".join(reflection["missing_points"]) if reflection["missing_points"] else "reflection approved"
        search_evaluation = update_search_evaluation(
            market_state["search_evaluation"],
            verdict=reflection_action_to_verdict(reflection["recommended_action"]),
            last_reason=reason,
        )
        logger.info(
            "Supervisor reflected market_analysis verdict=%s action=%s missing_dimensions=%s retry_count=%s revision_count=%s reason=%s",
            search_evaluation["verdict"],
            reflection["recommended_action"],
            reflection["missing_dimensions"],
            search_evaluation["retry_count"],
            search_evaluation["revision_count"],
            search_evaluation["last_reason"],
        )
        return {
            **market_state,
            "search_evaluation": search_evaluation,
            "reflection": reflection,
        }

    def _reflect_company_analysis(self, state: GraphState, state_key: str) -> dict | None:
        company_state = state[state_key]
        if not company_state["ready"]:
            return None

        agent_decision = company_state["agent_decision"]
        output = CompanyAnalysisOutput(
            core_competitiveness=company_state["core_competitiveness"],
            diversification_strategy=company_state["diversification_strategy"],
            evidence=company_state["evidence"],
            references=company_state["references"],
            missing_points=agent_decision["missing_points"],
            bias_checks=agent_decision["bias_checks"],
            missing_dimensions=agent_decision["missing_dimensions"],
            failure_type=agent_decision["failure_type"],
            recommended_action=agent_decision["recommended_action"],
            revision_needed=agent_decision["revision_needed"],
        )
        rule_reflection = assess_company_output(output, company_state["references"])
        llm_action = agent_decision["recommended_action"]
        llm_missing_points = agent_decision["missing_points"]
        llm_missing_dimensions = filter_company_missing_dimensions(agent_decision["missing_dimensions"])
        has_minimum_signal = self._has_minimum_company_signal(
            company_state["core_competitiveness"],
            company_state["diversification_strategy"],
            company_state["evidence"],
            company_state["references"],
        )
        if has_minimum_signal and rule_reflection["recommended_action"] == "accept":
            llm_action = "accept"
            llm_missing_points = []
            llm_missing_dimensions = []

        reflection = build_reflection(
            focus="company core analysis with agentic RAG",
            llm_missing_points=llm_missing_points,
            llm_bias_checks=agent_decision["bias_checks"],
            llm_missing_dimensions=llm_missing_dimensions,
            llm_failure_type=agent_decision["failure_type"],
            llm_action=llm_action,
            rule_missing_points=rule_reflection["missing_points"],
            rule_bias_checks=rule_reflection["bias_checks"],
            rule_missing_dimensions=rule_reflection["missing_dimensions"],
            rule_failure_type=rule_reflection["failure_type"],
            rule_action=rule_reflection["recommended_action"],
        )
        if has_minimum_signal and not reflection["missing_points"] and not reflection["missing_dimensions"]:
            reflection = {
                **reflection,
                "failure_type": "none",
                "recommended_action": "accept",
                "revision_needed": False,
            }
        if has_minimum_signal and reflection["recommended_action"] == "accept":
            verdict = "approved"
        else:
            verdict = reflection_action_to_verdict(reflection["recommended_action"])

        reason = "; ".join(reflection["missing_points"]) if reflection["missing_points"] else "reflection approved"
        search_evaluation = update_search_evaluation(
            company_state["search_evaluation"],
            verdict=verdict,
            last_reason=reason,
        )
        logger.info(
            "Supervisor reflected %s verdict=%s action=%s missing_dimensions=%s retry_count=%s revision_count=%s reason=%s",
            state_key,
            search_evaluation["verdict"],
            reflection["recommended_action"],
            reflection["missing_dimensions"],
            search_evaluation["retry_count"],
            search_evaluation["revision_count"],
            search_evaluation["last_reason"],
        )
        return {
            **company_state,
            "search_evaluation": search_evaluation,
            "reflection": reflection,
        }

    def _reflect_report_phase(self, state: GraphState) -> dict:
        report_state = state["report"]
        if not report_state["ready"]:
            return {}

        agent_decision = report_state["agent_decision"]
        output = ReportOutput(
            title=report_state["title"],
            summary=report_state["summary"],
            markdown_body=report_state["markdown_body"],
            references=report_state["references"],
            missing_points=agent_decision["missing_points"],
            bias_checks=agent_decision["bias_checks"],
            missing_dimensions=agent_decision["missing_dimensions"],
            failure_type=agent_decision["failure_type"],
            recommended_action=agent_decision["recommended_action"],
            revision_needed=agent_decision["revision_needed"],
        )
        rule_reflection = assess_report_output(
            output,
            report_state["markdown_body"],
            report_state["references"],
            report_state["quality_check"],
        )
        reflection = build_reflection(
            focus="report quality check before PDF generation",
            llm_missing_points=agent_decision["missing_points"],
            llm_bias_checks=agent_decision["bias_checks"],
            llm_missing_dimensions=agent_decision["missing_dimensions"],
            llm_failure_type=agent_decision["failure_type"],
            llm_action=agent_decision["recommended_action"],
            rule_missing_points=rule_reflection["missing_points"],
            rule_bias_checks=rule_reflection["bias_checks"],
            rule_missing_dimensions=rule_reflection["missing_dimensions"],
            rule_failure_type=rule_reflection["failure_type"],
            rule_action=rule_reflection["recommended_action"],
        )
        reason = "; ".join(reflection["missing_points"]) if reflection["missing_points"] else "report quality approved"
        search_evaluation = update_search_evaluation(
            report_state["search_evaluation"],
            verdict=reflection_action_to_verdict(reflection["recommended_action"]),
            last_reason=reason,
        )
        logger.info(
            "Supervisor reflected report verdict=%s action=%s missing_dimensions=%s retry_count=%s revision_count=%s reason=%s",
            search_evaluation["verdict"],
            reflection["recommended_action"],
            reflection["missing_dimensions"],
            search_evaluation["retry_count"],
            search_evaluation["revision_count"],
            search_evaluation["last_reason"],
        )
        return {
            "report": {
                **report_state,
                "search_evaluation": search_evaluation,
                "reflection": reflection,
            }
        }

    @staticmethod
    def _apply_updates(state: GraphState, updates: dict) -> GraphState:
        if not updates:
            return state
        merged = dict(state)
        merged.update(updates)
        return merged  # type: ignore[return-value]

    @staticmethod
    def _has_minimum_company_signal(
        core_competitiveness: list[str],
        diversification_strategy: list[str],
        evidence: list[str],
        references: list[str],
    ) -> bool:
        return (
            len(core_competitiveness) >= 2
            and len(diversification_strategy) >= 2
            and len(evidence) >= 3
            and len(references) >= 3
        )

    @staticmethod
    def _has_minimum_market_signal(
        market_view: str,
        evidence: list[str],
        references: list[str],
    ) -> bool:
        return bool(market_view.strip()) and len(evidence) >= 6 and len(references) >= 3

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
