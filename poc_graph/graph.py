from __future__ import annotations

from .builder import GraphBuilder
from .registry import GraphRegistry
from .runner import GraphRunner
from .spec import (
    AGENT_ROLE_OVERVIEW,
    FIXED_USER_PROMPT,
    GRAPH_EDGES,
    GRAPH_NODES,
    MERMAID_OVERVIEW,
    SUPERVISOR_ROUTE_MAP,
)


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


def build_graph():
    return GraphBuilder().build()


def run_simulation(raw_user_query: str = FIXED_USER_PROMPT):
    return GraphRunner().run_simulation(raw_user_query)


if __name__ == "__main__":
    runner = GraphRunner()
    final_state, execution_trace = runner.run_simulation(FIXED_USER_PROMPT)
    runner.print_mermaid_overview()
    print()
    print("Execution Trace:")
    for item in execution_trace:
        print(f"- {item}")
    print()
    print("Final Phase:", final_state["supervisor"]["workflow_phase"])
