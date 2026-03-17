from __future__ import annotations

from .registry import GraphRegistry
from .spec import SUPERVISOR_ROUTE_MAP
from .state_models import GraphState


class GraphBuilder:
    def __init__(self, registry: GraphRegistry | None = None) -> None:
        self.registry = registry or GraphRegistry()

    def route_from_supervisor(self, state: GraphState) -> str:
        phase = state["supervisor"]["workflow_phase"]
        return SUPERVISOR_ROUTE_MAP.get(phase, "end")

    def build(self):
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(GraphState)

        graph.add_node(self.registry.supervisor.name, self.registry.supervisor.run)
        graph.add_node(self.registry.initial_parallel_fanout.name, self.registry.initial_parallel_fanout.run)
        graph.add_node(self.registry.market_analysis.name, self.registry.market_analysis.run)
        graph.add_node(self.registry.lges_core.name, self.registry.lges_core.run)
        graph.add_node(self.registry.catl_core.name, self.registry.catl_core.run)
        graph.add_node(self.registry.initial_parallel_join.name, self.registry.initial_parallel_join.run)
        graph.add_node(self.registry.swot_parallel_fanout.name, self.registry.swot_parallel_fanout.run)
        graph.add_node(self.registry.lges_swot.name, self.registry.lges_swot.run)
        graph.add_node(self.registry.catl_swot.name, self.registry.catl_swot.run)
        graph.add_node(self.registry.swot_parallel_join.name, self.registry.swot_parallel_join.run)
        graph.add_node(self.registry.comparison.name, self.registry.comparison.run)
        graph.add_node(self.registry.report.name, self.registry.report.run)

        graph.add_edge(START, self.registry.supervisor.name)

        graph.add_conditional_edges(
            self.registry.supervisor.name,
            self.route_from_supervisor,
            {
                "initial_parallel_fanout": self.registry.initial_parallel_fanout.name,
                "swot_parallel_fanout": self.registry.swot_parallel_fanout.name,
                "strategic_comparison_agent": self.registry.comparison.name,
                "pdf_report_agent": self.registry.report.name,
                "end": END,
            },
        )

        graph.add_edge(self.registry.initial_parallel_fanout.name, self.registry.market_analysis.name)
        graph.add_edge(self.registry.initial_parallel_fanout.name, self.registry.lges_core.name)
        graph.add_edge(self.registry.initial_parallel_fanout.name, self.registry.catl_core.name)
        graph.add_edge(self.registry.market_analysis.name, self.registry.initial_parallel_join.name)
        graph.add_edge(self.registry.lges_core.name, self.registry.initial_parallel_join.name)
        graph.add_edge(self.registry.catl_core.name, self.registry.initial_parallel_join.name)
        graph.add_edge(self.registry.initial_parallel_join.name, self.registry.supervisor.name)

        graph.add_edge(self.registry.swot_parallel_fanout.name, self.registry.lges_swot.name)
        graph.add_edge(self.registry.swot_parallel_fanout.name, self.registry.catl_swot.name)
        graph.add_edge(self.registry.lges_swot.name, self.registry.swot_parallel_join.name)
        graph.add_edge(self.registry.catl_swot.name, self.registry.swot_parallel_join.name)
        graph.add_edge(self.registry.swot_parallel_join.name, self.registry.supervisor.name)

        graph.add_edge(self.registry.comparison.name, self.registry.supervisor.name)
        graph.add_edge(self.registry.report.name, self.registry.supervisor.name)

        return graph.compile()

