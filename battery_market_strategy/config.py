from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    package_root: Path
    data_dir: Path
    cache_dir: Path
    faiss_root: Path
    output_dir: Path
    lges_pdf_path: Path
    catl_pdf_path: Path
    llm_model: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    max_rag_rounds: int
    openai_api_key: str
    tavily_api_key: str

    @property
    def lges_index_dir(self) -> Path:
        return self.faiss_root / "lges"

    @property
    def catl_index_dir(self) -> Path:
        return self.faiss_root / "catl"

    @property
    def log_dir(self) -> Path:
        return self.output_dir / "logs"

    @property
    def log_file_path(self) -> Path:
        return self.log_dir / "battery_strategy.log"


def load_config() -> AppConfig:
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent

    load_dotenv(project_root / "key.env")

    default_data_dir = project_root / "data"
    fallback_data_dir = package_root / "data"
    data_dir = Path(os.getenv("DATA_DIR", default_data_dir if default_data_dir.exists() else fallback_data_dir))
    cache_dir = Path(os.getenv("CACHE_DIR", project_root / ".cache" / "battery_market_strategy"))
    faiss_root = cache_dir / "faiss"
    default_output_dir = project_root / "output"
    fallback_output_dir = package_root / "output"
    output_dir = Path(
        os.getenv("OUTPUT_DIR", default_output_dir if default_output_dir.exists() else fallback_output_dir)
    )
    local_embedding_model_dir = project_root / "models" / "bge-m3"
    default_embedding_model = local_embedding_model_dir if local_embedding_model_dir.exists() else "BAAI/bge-m3"

    return AppConfig(
        project_root=project_root,
        package_root=package_root,
        data_dir=data_dir,
        cache_dir=cache_dir,
        faiss_root=faiss_root,
        output_dir=output_dir,
        lges_pdf_path=Path(os.getenv("LGES_PDF_PATH", data_dir / "LGES.pdf")),
        catl_pdf_path=Path(os.getenv("CATL_PDF_PATH", data_dir / "CATL.pdf")),
        llm_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        embedding_model=os.getenv("EMBEDDING_MODEL", str(default_embedding_model)),
        chunk_size=int(os.getenv("CHUNK_SIZE", "1200")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
        top_k=int(os.getenv("RETRIEVER_TOP_K", "5")),
        max_rag_rounds=int(os.getenv("MAX_RAG_ROUNDS", "2")),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
    )
