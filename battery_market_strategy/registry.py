from __future__ import annotations

from .config import AppConfig, load_config
from .logging_utils import setup_logging
from .agents import (
    CATLCorePortfolioAgent,
    CATLSWOTAgent,
    LGESCorePortfolioAgent,
    LGESSWOTAgent,
    MarketAnalysisAgent,
    PDFReportAgent,
    StrategicComparisonAgent,
    SupervisorAgent,
)
from .orchestration import (
    InitialParallelFanOut,
    InitialParallelJoin,
    SWOTParallelFanOut,
    SWOTParallelJoin,
)
from .services import AgenticRAGService, CompanyVectorStoreService, LLMService, ReportService, WebSearchService


class GraphRegistry:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        setup_logging(self.config)

        self.llm_service = LLMService(self.config)
        self.web_search_service = WebSearchService(self.config)
        self.vector_store_service = CompanyVectorStoreService(self.config)
        self.rag_service = AgenticRAGService(
            self.llm_service,
            self.vector_store_service,
            self.web_search_service,
            self.config.max_rag_rounds,
        )
        self.report_service = ReportService(self.config)

        self.supervisor = SupervisorAgent()
        self.initial_parallel_fanout = InitialParallelFanOut()
        self.market_analysis = MarketAnalysisAgent(self.llm_service, self.web_search_service)
        self.lges_core = LGESCorePortfolioAgent(
            self.config,
            self.llm_service,
            self.rag_service,
            self.vector_store_service,
        )
        self.catl_core = CATLCorePortfolioAgent(
            self.config,
            self.llm_service,
            self.rag_service,
            self.vector_store_service,
        )
        self.initial_parallel_join = InitialParallelJoin()
        self.swot_parallel_fanout = SWOTParallelFanOut()
        self.lges_swot = LGESSWOTAgent(self.llm_service)
        self.catl_swot = CATLSWOTAgent(self.llm_service)
        self.swot_parallel_join = SWOTParallelJoin()
        self.comparison = StrategicComparisonAgent(self.llm_service)
        self.report = PDFReportAgent(self.llm_service, self.report_service)
