"""文档检索器 —— 基于 LangChain TFIDFRetriever 的轻量级文档搜索

使用 scikit-learn TfidfVectorizer（字符级 n-gram），零外部向量数据库依赖。
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from langchain_community.retrievers import TFIDFRetriever
from langchain_core.documents import Document


class Retriever:
    """TF-IDF 检索器 —— 封装 LangChain TFIDFRetriever，带相关性分数过滤"""

    def __init__(self):
        self._retriever: TFIDFRetriever | None = None
        self.chunks: list[str] = []

    def index(self, chunks: list[str]) -> None:
        """用新的分块列表重建索引"""
        self.chunks = chunks
        if not chunks:
            self._retriever = None
            return

        self._retriever = TFIDFRetriever.from_texts(
            texts=chunks,
            tfidf_params={
                "analyzer": "char",
                "ngram_range": (1, 3),
                "max_features": 5000,
            },
        )

    def search(self, query: str, top_k: int = 5) -> list[Document]:
        """搜索 top_k 个最相关的分块，返回 LangChain Document 列表"""
        if self._retriever is None or not self.chunks:
            return []

        try:
            query_vec = self._retriever.vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self._retriever.tfidf_array).flatten()
            top_indices = np.argsort(scores)[::-1][:top_k]

            results = []
            for idx in top_indices:
                if scores[idx] > 0.01:
                    results.append(self._retriever.docs[idx])
            return results
        except Exception:
            return []


# 全局单例
_retriever = Retriever()


def get_retriever() -> Retriever:
    return _retriever


def rebuild_index(chunks: list[str]) -> None:
    _retriever.index(chunks)


def search_chunks(query: str, top_k: int = 5) -> list[Document]:
    return _retriever.search(query, top_k)
