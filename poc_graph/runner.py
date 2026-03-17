from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .config import AppConfig
from .registry import GraphRegistry
from .spec import MERMAID_OVERVIEW, SUPERVISOR_ROUTE_MAP
from .state_factory import make_initial_state
from .state_models import GraphState

logger = logging.getLogger(__name__)


class GraphRunner:
    def __init__(self, registry: GraphRegistry | None = None, config: AppConfig | None = None) -> None:
        self.registry = registry or GraphRegistry(config=config)
        self.config = self.registry.config

    def print_mermaid_overview(self) -> None:
        print(MERMAID_OVERVIEW)

    def route_from_supervisor(self, state: GraphState) -> str:
        phase = state["supervisor"]["workflow_phase"]
        return SUPERVISOR_ROUTE_MAP.get(phase, "end")

    def run_simulation(self, raw_user_query: str) -> tuple[GraphState, list[str]]:
        logger.info("Starting graph simulation")
        state = make_initial_state(raw_user_query, self.config)
        trace: list[str] = []

        try:
            while True:
                state = self._mark_control(state, self.registry.supervisor.name)
                state = self._merge_state(state, self.registry.supervisor.run(state))
                trace.append(f"supervisor:{state['supervisor']['workflow_phase']}")

                route = self.route_from_supervisor(state)
                trace.append(f"route:{route}")

                if route == "end":
                    state = self._set_end_flag(state)
                    break

                if route == self.registry.initial_parallel_fanout.name:
                    state = self._mark_control(state, self.registry.initial_parallel_fanout.name)
                    state = self._merge_state(state, self.registry.initial_parallel_fanout.run(state))
                    trace.append(self.registry.initial_parallel_fanout.name)
                    state = self._run_parallel_agents(
                        state,
                        [
                            self.registry.market_analysis,
                            self.registry.lges_core,
                            self.registry.catl_core,
                        ],
                        trace,
                    )
                    state = self._mark_control(state, self.registry.initial_parallel_join.name)
                    state = self._merge_state(state, self.registry.initial_parallel_join.run(state))
                    trace.append(self.registry.initial_parallel_join.name)
                    continue

                if route == self.registry.swot_parallel_fanout.name:
                    state = self._mark_control(state, self.registry.swot_parallel_fanout.name)
                    state = self._merge_state(state, self.registry.swot_parallel_fanout.run(state))
                    trace.append(self.registry.swot_parallel_fanout.name)
                    state = self._run_parallel_agents(
                        state,
                        [
                            self.registry.lges_swot,
                            self.registry.catl_swot,
                        ],
                        trace,
                    )
                    state = self._mark_control(state, self.registry.swot_parallel_join.name)
                    state = self._merge_state(state, self.registry.swot_parallel_join.run(state))
                    trace.append(self.registry.swot_parallel_join.name)
                    continue

                if route == self.registry.comparison.name:
                    state = self._mark_control(state, self.registry.comparison.name)
                    state = self._merge_state(state, self.registry.comparison.run(state))
                    trace.append(self.registry.comparison.name)
                    continue

                if route == self.registry.report.name:
                    state = self._mark_control(state, self.registry.report.name)
                    state = self._merge_state(state, self.registry.report.run(state))
                    trace.append(self.registry.report.name)
                    continue

                raise ValueError(f"Unknown route: {route}")
        except Exception as exc:
            state = self._set_failure(state, str(exc))
            raise

        return state, trace

    def _run_parallel_agents(self, state: GraphState, agents: list[Any], trace: list[str]) -> GraphState:
        updated_state = state
        with ThreadPoolExecutor(max_workers=len(agents)) as executor:
            futures = {}
            for agent in agents:
                updated_state = self._mark_control(updated_state, agent.name)
                futures[executor.submit(agent.run, updated_state)] = agent.name
            for future in as_completed(futures):
                agent_name = futures[future]
                logger.info("Waiting completed agent=%s", agent_name)
                update = future.result()
                updated_state = self._merge_state(updated_state, update)
                trace.append(agent_name)
        return updated_state

    @staticmethod
    def _mark_control(state: GraphState, node_name: str) -> GraphState:
        control = state["control"]
        step_count = control["step_count"] + 1
        updated = GraphRunner._merge_state(
            state,
            {
                "control": {
                    **control,
                    "current_node": node_name,
                    "step_count": step_count,
                }
            },
        )
        if step_count > control["max_step_count"]:
            raise RuntimeError(f"Exceeded max_step_count={control['max_step_count']} at node={node_name}")
        return updated

    @staticmethod
    def _set_end_flag(state: GraphState) -> GraphState:
        return GraphRunner._merge_state(
            state,
            {
                "control": {
                    **state["control"],
                    "current_node": "end",
                    "end_flag": True,
                }
            },
        )

    @staticmethod
    def _set_failure(state: GraphState, fail_reason: str) -> GraphState:
        return GraphRunner._merge_state(
            state,
            {
                "control": {
                    **state["control"],
                    "fail_reason": fail_reason,
                    "end_flag": True,
                }
            },
        )

    @staticmethod
    def _merge_state(base: GraphState, update: dict[str, Any]) -> GraphState:
        merged: dict[str, Any] = dict(base)
        for key, value in update.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged  # type: ignore[return-value]


def main() -> None:
    from .spec import FIXED_USER_PROMPT

    runner = GraphRunner()
    final_state, execution_trace = runner.run_simulation(FIXED_USER_PROMPT)
    print("Execution Trace:")
    for item in execution_trace:
        print(f"- {item}")
    print()
    print("Report PDF:", final_state["report"]["pdf_path"])
    print("Report Markdown:", final_state["report"]["markdown_path"])


if __name__ == "__main__":
    main()
