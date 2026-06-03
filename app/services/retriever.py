"""文档检索器 —— TF-IDF 字面关键词检索（scikit-learn）

不依赖任何外部向量数据库，使用字符级 n-gram TF-IDF 进行文本匹配，
天然支持中英文混合场景。数据存储在 SQLite 中，检索在进程内完成。
"""

import logging

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)


class Retriever:
    """TF-IDF 文本检索引擎"""

    def __init__(self):
        self._vectorizer: TfidfVectorizer | None = None
        self._tfidf_matrix: np.ndarray | None = None
        self._texts: list[str] = []
        self._metadatas: list[dict] = []

    def index(self, doc_chunks: list[tuple[str, str]]) -> None:
        """重建 TF-IDF 索引。

        Args:
            doc_chunks: [(doc_id, chunk_content), ...]
        """
        if not doc_chunks:
            return

        doc_ids, contents = zip(*doc_chunks)
        self._metadatas = [{"doc_id": did} for did in doc_ids]

        try:
            self._vectorizer = TfidfVectorizer(
                analyzer="char",
                ngram_range=(1, 3),
            )
            self._tfidf_matrix = self._vectorizer.fit_transform(contents)
            self._texts = list(contents)
            logger.info("TF-IDF 索引重建完成，共 %d 个分块", len(doc_chunks))
        except Exception as e:
            logger.error("TF-IDF 索引重建失败: %s", e)

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_id: str | None = None,
    ) -> list[Document]:
        """搜索最相关的分块。

        Args:
            query: 用户问题。
            top_k: 返回结果数。
            doc_id: 可选，限定搜索某个文档。

        Returns:
            list[Document]: page_content 为文本，metadata 含 score 和 doc_id。
        """
        if self._vectorizer is None or self._tfidf_matrix is None:
            return []

        try:
            query_vec = self._vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self._tfidf_matrix).flatten()

            top_indices = scores.argsort()[-top_k:][::-1]

            docs = []
            for idx in top_indices:
                if scores[idx] <= 0:
                    continue
                meta = dict(self._metadatas[idx])
                if doc_id and meta.get("doc_id") != doc_id:
                    continue
                docs.append(Document(
                    page_content=self._texts[idx],
                    metadata={
                        "score": float(scores[idx]),
                        "doc_id": meta.get("doc_id", ""),
                    },
                ))
            return docs
        except Exception as e:
            logger.error("TF-IDF 搜索失败: %s", e)
            return []


# ── 全局单例 ──────────────────────────────────────────────

_retriever = Retriever()


def get_retriever() -> Retriever:
    return _retriever


def rebuild_index(doc_chunks: list[tuple[str, str]]) -> None:
    _retriever.index(doc_chunks)


def search_chunks(
    query: str,
    top_k: int = 5,
    doc_id: str | None = None,
) -> list[Document]:
    return _retriever.search(query, top_k, doc_id=doc_id)
