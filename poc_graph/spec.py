from __future__ import annotations


FIXED_USER_PROMPT = (
    "LG에너지 솔루션과 CATL 두 기업에 대해 배터리 산업에 관련된 시장 파악, "
    "핵심 기술력, 포트폴리오 다각화 전략에 대해 조사하고, 두 기업의 전략적 차이점과 "
    "강약점을 객관적인 데이터 기반으로 분석하는 배터리 시장 전략 보고서를 작성해줘"
)

DEFAULT_REPORT_TITLE = "배터리 시장 전략 보고서: LG에너지솔루션 vs CATL"
MAX_STEP_COUNT = 40
INITIAL_SEARCH_MAX_RETRY = 2
INITIAL_SEARCH_MAX_REVISION = 2
REPORT_MAX_RETRY = 1
REPORT_MAX_REVISION = 1

GRAPH_NODES = [
    "supervisor_agent",
    "initial_parallel_fanout",
    "market_analysis_agent",
    "lges_core_portfolio_agent",
    "catl_core_portfolio_agent",
    "initial_parallel_join",
    "swot_parallel_fanout",
    "lges_swot_agent",
    "catl_swot_agent",
    "swot_parallel_join",
    "strategic_comparison_agent",
    "pdf_report_agent",
]


GRAPH_EDGES = [
    ("START", "supervisor_agent"),
    ("supervisor_agent", "initial_parallel_fanout"),
    ("initial_parallel_fanout", "market_analysis_agent"),
    ("initial_parallel_fanout", "lges_core_portfolio_agent"),
    ("initial_parallel_fanout", "catl_core_portfolio_agent"),
    ("market_analysis_agent", "initial_parallel_join"),
    ("lges_core_portfolio_agent", "initial_parallel_join"),
    ("catl_core_portfolio_agent", "initial_parallel_join"),
    ("initial_parallel_join", "supervisor_agent"),
    ("supervisor_agent", "swot_parallel_fanout"),
    ("swot_parallel_fanout", "lges_swot_agent"),
    ("swot_parallel_fanout", "catl_swot_agent"),
    ("lges_swot_agent", "swot_parallel_join"),
    ("catl_swot_agent", "swot_parallel_join"),
    ("swot_parallel_join", "supervisor_agent"),
    ("supervisor_agent", "strategic_comparison_agent"),
    ("strategic_comparison_agent", "supervisor_agent"),
    ("supervisor_agent", "pdf_report_agent"),
    ("pdf_report_agent", "supervisor_agent"),
    ("supervisor_agent", "END"),
]


MERMAID_OVERVIEW = """
flowchart TD
    START([START]) --> supervisor[Supervisor Agent]

    supervisor --> initial_fanout[Initial Parallel Fan-out]
    initial_fanout --> market[Market Analysis Agent]
    initial_fanout --> lges_core[LGES Core Competitiveness and Portfolio Diversification Agent]
    initial_fanout --> catl_core[CATL Core Competitiveness and Portfolio Diversification Agent]

    market --> initial_join[Initial Parallel Join]
    lges_core --> initial_join
    catl_core --> initial_join
    initial_join --> supervisor

    supervisor --> swot_fanout[SWOT Parallel Fan-out]
    swot_fanout --> lges_swot[LGES SWOT Agent]
    swot_fanout --> catl_swot[CATL SWOT Agent]

    lges_swot --> swot_join[SWOT Parallel Join]
    catl_swot --> swot_join
    swot_join --> supervisor

    supervisor --> compare[Strategic Comparison Agent]
    compare --> supervisor

    supervisor --> report[PDF Report Agent]
    report --> supervisor

    supervisor --> END([END])
""".strip()


AGENT_ROLE_OVERVIEW = """
Initial parallel phase:
- Market Analysis Agent
- LGES Core Competitiveness and Portfolio Diversification Agent
- CATL Core Competitiveness and Portfolio Diversification Agent

SWOT parallel phase:
- LGES SWOT Agent
- CATL SWOT Agent

Final serial phase:
- Strategic Comparison Agent
- PDF Report Agent
""".strip()


SUPERVISOR_ROUTE_MAP = {
    "initial_parallel": "initial_parallel_fanout",
    "swot_parallel": "swot_parallel_fanout",
    "comparison": "strategic_comparison_agent",
    "reporting": "pdf_report_agent",
    "done": "end",
}
