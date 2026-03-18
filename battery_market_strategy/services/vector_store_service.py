from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class EnsureIndexResult:
    document_hash: str
    index_ready: bool
    needs_reindex: bool
    manifest_path: Path
    index_dir: Path


class CompanyVectorStoreService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._config.faiss_root.mkdir(parents=True, exist_ok=True)
        logger.info("Initializing embeddings model=%s", config.embedding_model)
        self._embeddings = HuggingFaceEmbeddings(
            model_name=config.embedding_model,
            model_kwargs={"trust_remote_code": True},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

    @property
    def embedding_model_name(self) -> str:
        return self._config.embedding_model

    def ensure_index(self, company_id: str, pdf_path: Path, index_dir: Path) -> EnsureIndexResult:
        if not pdf_path.exists():
            raise FileNotFoundError(f"Source PDF not found for {company_id}: {pdf_path}")
        index_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = index_dir / "manifest.json"
        document_hash = self._calculate_hash(pdf_path)
        current_manifest = self._read_manifest(manifest_path)
        expected_files = [index_dir / "index.faiss", index_dir / "index.pkl"]

        if (
            current_manifest
            and current_manifest.get("document_hash") == document_hash
            and current_manifest.get("embedding_model") == self._config.embedding_model
            and all(path.exists() for path in expected_files)
        ):
            logger.info("Reusing cached FAISS index company=%s index_dir=%s", company_id, index_dir)
            return EnsureIndexResult(
                document_hash=document_hash,
                index_ready=True,
                needs_reindex=False,
                manifest_path=manifest_path,
                index_dir=index_dir,
            )

        logger.info("Building FAISS index company=%s pdf=%s", company_id, pdf_path)
        documents = self._load_and_split_pdf(pdf_path, company_id)
        vector_store = FAISS.from_documents(documents, self._embeddings)
        vector_store.save_local(str(index_dir))
        manifest = {
            "company_id": company_id,
            "document_hash": document_hash,
            "embedding_model": self._config.embedding_model,
            "source_pdf": str(pdf_path),
            "chunk_count": len(documents),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return EnsureIndexResult(
            document_hash=document_hash,
            index_ready=True,
            needs_reindex=True,
            manifest_path=manifest_path,
            index_dir=index_dir,
        )

    def retrieve(self, index_dir: Path, query: str, top_k: int) -> list[tuple[Document, float]]:
        logger.info("Retrieving from FAISS index_dir=%s top_k=%s query=%s", index_dir, top_k, query)
        vector_store = FAISS.load_local(
            str(index_dir),
            self._embeddings,
            allow_dangerous_deserialization=True,
        )
        return vector_store.similarity_search_with_score(query, k=top_k)

    def _load_and_split_pdf(self, pdf_path: Path, company_id: str) -> list[Document]:
        loader = PyPDFLoader(str(pdf_path))
        documents = loader.load()
        split_docs = self._splitter.split_documents(documents)
        logger.info(
            "Loaded and split PDF company=%s pages=%s chunks=%s",
            company_id,
            len(documents),
            len(split_docs),
        )
        enriched_docs: list[Document] = []
        for idx, doc in enumerate(split_docs):
            metadata = dict(doc.metadata)
            metadata["company_id"] = company_id
            metadata["chunk_id"] = f"{company_id.lower()}-chunk-{idx}"
            enriched_docs.append(Document(page_content=doc.page_content, metadata=metadata))
        return enriched_docs

    @staticmethod
    def _calculate_hash(pdf_path: Path) -> str:
        digest = hashlib.sha256()
        with pdf_path.open("rb") as file:
            for chunk in iter(lambda: file.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _read_manifest(manifest_path: Path) -> dict | None:
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
