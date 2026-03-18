# Lazy imports so PDF-only runs (render_pdf) don't need langchain etc.
__all__ = [
    "LLMService",
    "AgenticRAGService",
    "ReportService",
    "CompanyVectorStoreService",
    "WebSearchService",
    "PremiumReportService",
]


def __getattr__(name: str):
    if name == "LLMService":
        from .llm_service import LLMService
        return LLMService
    if name == "AgenticRAGService":
        from .rag_service import AgenticRAGService
        return AgenticRAGService
    if name == "ReportService":
        from .report_service import ReportService
        return ReportService
    if name == "CompanyVectorStoreService":
        from .vector_store_service import CompanyVectorStoreService
        return CompanyVectorStoreService
    if name == "WebSearchService":
        from .web_search_service import WebSearchService
        return WebSearchService
    if name == "PremiumReportService":
        from .report_service import PremiumReportService
        return PremiumReportService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
