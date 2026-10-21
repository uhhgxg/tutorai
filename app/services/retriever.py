"""ChromaDB 向量检索 —— 基于 sentence-transformers 嵌入

将 ChromaDB 嵌入函数设为 sentence-transformers (bge-small-zh) 模型
提供中文文档的高质量语义检索
"""

import hashlib
import logging
import math
import re
import threading
from collections import defaultdict

from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_EMBED_MODEL = "BAAI/bge-small-zh-v1.5"
CHROMA_PERSIST_DIR = "./data/chroma_db"


class HashEmbeddingFunction:
    """无外部模型的确定性嵌入，仅用于测试和离线诊断。"""

    dimension = 256

    @staticmethod
    def name() -> str:
        return "tutorai-hash"

    def is_legacy(self) -> bool:
        return False

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict[str, str]:
        return {"name": self.name()}

    @staticmethod
    def build_from_config(config: dict) -> "HashEmbeddingFunction":
        return HashEmbeddingFunction()

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            vector = [0.0] * self.dimension
            for term in _tokenize(text):
                digest = hashlib.sha256(term.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                vector[index] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)


class Retriever:
    """ChromaDB 向量检索器"""

    def __init__(
        self,
        client: object | None = None,
        embedding_function=None,
    ):
        if client is not None:
            self._client = client
        else:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=CHROMA_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False),
            )

        if embedding_function is not None:
            self._embedding_fn = embedding_function
        else:
            try:
                from chromadb.utils.embedding_functions import (
                    SentenceTransformerEmbeddingFunction,
                )
                self._embedding_fn = SentenceTransformerEmbeddingFunction(
                    model_name=DEFAULT_EMBED_MODEL
                )
            except Exception as exc:
                logger.error("无法加载嵌入模型 %s: %s", DEFAULT_EMBED_MODEL, exc)
                raise RuntimeError(
                    "无法加载本地嵌入模型，请先缓存 BGE 模型，或为测试注入 embedding_function"
                ) from exc

        self._collection = self._client.get_or_create_collection(
            name="tutorai_docs",
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Retriever initialized (collection size: %d)", self._collection.count()
        )

    def index(self, doc_id: str, user_id: str, chunks: list[str]) -> None:
        """将文档分块加入向量索引
        Args:
            doc_id: 文档 ID
            user_id: 用户 ID（用于数据隔离）
            chunks: 文本分块列表
        """
        if not chunks:
            return

        self.remove_document(doc_id)

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {"doc_id": doc_id, "user_id": user_id, "chunk_index": i}
            for i in range(len(chunks))
        ]

        self._collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        logger.info(
            "Indexed %d chunks for document %s (user %s)",
            len(chunks), doc_id, user_id,
        )

    def remove_document(self, doc_id: str) -> None:
        """从索引中删除指定文档的所有分块"""
        try:
            self._collection.delete(where={"doc_id": doc_id})
            logger.info("Removed document %s from index", doc_id)
        except Exception as e:
            logger.warning("Failed to remove document %s from index: %s", doc_id, e)

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_id: str | None = None,
        user_id: str | None = None,
        min_score: float = 0.0,
    ) -> list[Document]:
        """语义搜索相关文档片段
        Args:
            query: 查询文本
            top_k: 返回结果数量
            doc_id: 限定搜索的文档 ID
            user_id: 限定搜索的用户 ID
        Returns:
            list[Document]: page_content 为文本，metadata 含 score / doc_id / user_id
        """
        if not query.strip() or top_k <= 0:
            return []

        where_filters = {}
        if doc_id is not None:
            where_filters["doc_id"] = doc_id
        if user_id is not None:
            where_filters["user_id"] = user_id

        try:
            candidate_k = max(top_k, top_k * settings.retrieval_candidate_multiplier)
            n_results = min(candidate_k, max(self._collection.count(), 1))
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filters or None,
            )
        except Exception as e:
            logger.error("ChromaDB query failed: %s", e)
            return []

        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        docs = []
        query_terms = _tokenize(query)
        for i, content in enumerate(results["documents"][0]):
            meta = (
                results["metadatas"][0][i]
                if results.get("metadatas") and results["metadatas"][0]
                else {}
            )
            distance = (
                results["distances"][0][i]
                if results.get("distances") and results["distances"][0]
                else 0
            )
            semantic_score = max(0.0, 1.0 - float(distance))
            lexical_score = _lexical_score(query_terms, _tokenize(content))
            # 语义召回负责泛化，关键词得分负责术语/编号等精确匹配。
            score = 0.75 * semantic_score + 0.25 * lexical_score
            if score < min_score:
                continue

            docs.append(
                Document(
                    page_content=content,
                    metadata={
                        "score": score,
                        "semantic_score": semantic_score,
                        "lexical_score": lexical_score,
                        "doc_id": meta.get("doc_id", ""),
                        "user_id": meta.get("user_id", ""),
                        "chunk_index": meta.get("chunk_index", 0),
                        "source": f"{meta.get('doc_id', '')}#{meta.get('chunk_index', 0)}",
                    },
                )
            )
        docs.sort(key=lambda doc: doc.metadata.get("score", 0.0), reverse=True)
        return docs[:top_k]

    def reset(self) -> None:
        """清空所有索引"""
        try:
            existing = self._collection.get()
            if existing and existing.get("ids"):
                self._collection.delete(ids=existing["ids"])
            logger.info("Retriever index reset")
        except Exception as e:
            logger.error("Failed to reset retriever: %s", e)

    def count(self) -> int:
        """返回索引中的文档片段总数"""
        try:
            return self._collection.count()
        except Exception:
            return 0


_retriever: Retriever | None = None
_retriever_lock = threading.Lock()


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:
                _retriever = Retriever()
    return _retriever


def rebuild_index(chunks_with_meta: list[tuple[str, str, str]]) -> None:
    """重建整个索引
    Args:
        chunks_with_meta: [(doc_id, user_id, content), ...]
    """
    retriever = get_retriever()
    retriever.reset()
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for doc_id, user_id, content in chunks_with_meta:
        grouped[(doc_id, user_id)].append(content)
    for (doc_id, user_id), chunks in grouped.items():
        retriever.index(doc_id, user_id, chunks)
    if chunks_with_meta:
        logger.info("Index rebuilt with %d chunks", len(chunks_with_meta))


def search_chunks(
    query: str,
    top_k: int = 5,
    doc_id: str | None = None,
    user_id: str | None = None,
    min_score: float | None = None,
) -> list[Document]:
    """便捷函数：搜索相关文档片段"""
    threshold = settings.retrieval_score_threshold if min_score is None else min_score
    return get_retriever().search(
        query,
        top_k=top_k,
        doc_id=doc_id,
        user_id=user_id,
        min_score=threshold,
    )


def _tokenize(text: str) -> set[str]:
    """提取中英文术语；中文按 2-gram 处理，避免依赖额外分词服务。"""
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9_]+", lowered))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    terms.update(chinese[i : i + 2] for i in range(max(0, len(chinese) - 1)))
    return terms


def _lexical_score(query_terms: set[str], content_terms: set[str]) -> float:
    if not query_terms or not content_terms:
        return 0.0
    return len(query_terms & content_terms) / len(query_terms)
