from __future__ import annotations

import logging

from .builder import GraphBuilder
from .config import AppConfig
from .registry import GraphRegistry
from .spec import (
    AGENT_ROLE_OVERVIEW,
    FIXED_USER_PROMPT,
    GRAPH_EDGES,
    GRAPH_NODES,
    MERMAID_OVERVIEW,
    SUPERVISOR_ROUTE_MAP,
)
from .state_factory import make_initial_state
from .state_models import GraphState

logger = logging.getLogger(__name__)


def get_graph_spec() -> dict[str, object]:
    registry = GraphRegistry()
    return {
        "nodes": GRAPH_NODES,
        "edges": GRAPH_EDGES,
        "agents": {
            registry.supervisor.name: registry.supervisor.__class__.__name__,
            registry.market_analysis.name: registry.market_analysis.__class__.__name__,
            registry.lges_core.name: registry.lges_core.__class__.__name__,
            registry.catl_core.name: registry.catl_core.__class__.__name__,
            registry.lges_swot.name: registry.lges_swot.__class__.__name__,
            registry.catl_swot.name: registry.catl_swot.__class__.__name__,
            registry.comparison.name: registry.comparison.__class__.__name__,
            registry.report.name: registry.report.__class__.__name__,
        },
        "route_map": SUPERVISOR_ROUTE_MAP,
        "agent_role_overview": AGENT_ROLE_OVERVIEW,
    }


def print_mermaid_overview() -> None:
    print(MERMAID_OVERVIEW)


def build_graph(registry: GraphRegistry | None = None):
    return GraphBuilder(registry).build()


def run_workflow(
    raw_user_query: str = FIXED_USER_PROMPT,
    registry: GraphRegistry | None = None,
    config: AppConfig | None = None,
) -> tuple[GraphState, list[str]]:
    active_registry = registry or GraphRegistry(config=config)
    initial_state = make_initial_state(raw_user_query, active_registry.config)
    graph = build_graph(active_registry)
    logger.info("Starting workflow raw_user_query=%s", raw_user_query)
    final_state = graph.invoke(
        initial_state,
        config={"recursion_limit": initial_state["control"]["max_step_count"]},
    )
    logger.info(
        "Workflow finished phase=%s fail_reason=%s trace_len=%s",
        final_state["supervisor"]["workflow_phase"],
        final_state["control"]["fail_reason"],
        len(final_state["execution_trace"]),
    )
    return final_state, final_state["execution_trace"]


def main() -> None:
    final_state, execution_trace = run_workflow(FIXED_USER_PROMPT)
    print("Final Phase:", final_state["supervisor"]["workflow_phase"])
    if final_state["control"]["fail_reason"]:
        print("Fail Reason:", final_state["control"]["fail_reason"])
        print()
    print("Execution Trace:")
    for item in execution_trace:
        print(f"- {item}")
    print()
    print("Report PDF:", final_state["report"]["pdf_path"])
    print("Report Markdown:", final_state["report"]["markdown_path"])


if __name__ == "__main__":
    main()
