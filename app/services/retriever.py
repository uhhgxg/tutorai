"""文档检索器 —— ChromaDB 向量检索（sentence-transformers 本地嵌入）

从 TF-IDF 升级为向量检索，支持语义级匹配，无需外部 API 调用。
所有向量数据持久化在 ./data/chroma/ 目录中。
"""

import logging
from collections import defaultdict

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)


class Retriever:
    """ChromaDB 向量检索引擎"""

    def __init__(self, persist_dir: str = "./data/chroma", client=None):
        self._client = client or chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model,
        )
        self._collection = self._client.get_or_create_collection(
            name="document_chunks",
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def index(self, doc_id: str, user_id: str, chunks: list[str]) -> None:
        """将文档切片写入向量索引。

        Args:
            doc_id: 文档 ID。
            user_id: 所属用户 ID。
            chunks: 文本切片列表。
        """
        if not chunks:
            return
        self.remove_document(doc_id)
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "user_id": user_id} for _ in chunks]
        self._collection.add(
            documents=chunks, ids=ids, metadatas=metadatas,
        )
        logger.info("已索引文档 %s（%d 个分块）", doc_id, len(chunks))

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_id: str | None = None,
        user_id: str | None = None,
    ) -> list[Document]:
        """搜索最相关的分块。

        Args:
            query: 用户问题。
            top_k: 返回结果数。
            doc_id: 可选，限定搜索某个文档。
            user_id: 可选，按用户隔离。

        Returns:
            list[Document]: page_content 为文本，metadata 含 score 和 doc_id。
        """
        where_filters = {}
        if doc_id:
            where_filters["doc_id"] = doc_id
        if user_id:
            where_filters["user_id"] = user_id

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filters or None,
            )
        except Exception as e:
            logger.debug("ChromaDB 查询失败（可能索引为空）: %s", e)
            return []

        docs = []
        if not results.get("documents") or not results["documents"][0]:
            return docs

        documents = results["documents"][0]
        distances = results.get("distances", [[]])[0] or [0.0] * len(documents)
        metadatas = results.get("metadatas", [[]])[0] or [{}] * len(documents)

        for i, content in enumerate(documents):
            score = 1.0 - float(distances[i]) if i < len(distances) else 0.0
            meta = metadatas[i] if i < len(metadatas) else {}
            docs.append(Document(
                page_content=content,
                metadata={
                    "score": score,
                    "doc_id": meta.get("doc_id", ""),
                },
            ))
        return docs

    def remove_document(self, doc_id: str) -> None:
        """删除指定文档的所有切片"""
        try:
            self._collection.delete(where={"doc_id": doc_id})
            logger.info("已删除文档 %s 的索引", doc_id)
        except Exception as e:
            logger.debug("删除文档索引 %s 时出错: %s", doc_id, e)

    def rebuild_index(self, doc_chunks: list[tuple[str, str]]) -> None:
        """兼容接口：清空并重建所有文档的索引"""
        if not doc_chunks:
            return
        try:
            self._client.delete_collection("document_chunks")
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name="document_chunks",
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        groups = defaultdict(list)
        for doc_id, content in doc_chunks:
            groups[doc_id].append(content)
        for doc_id, chunks in groups.items():
            self.index(doc_id, user_id="unknown", chunks=chunks)
        logger.info("重建索引完成，共 %d 个分块", len(doc_chunks))


# ── 全局单例 ──────────────────────────────────────────────

_retriever = Retriever()


def get_retriever() -> Retriever:
    return _retriever


def rebuild_index(doc_chunks: list[tuple[str, str]]) -> None:
    _retriever.rebuild_index(doc_chunks)


def search_chunks(
    query: str,
    top_k: int = 5,
    doc_id: str | None = None,
    user_id: str | None = None,
) -> list[Document]:
    return _retriever.search(query, top_k, doc_id=doc_id, user_id=user_id)
