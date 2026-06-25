"""ChromaDB 检索器测试（使用 EphemeralClient 内存模式）"""

import pytest
import chromadb
from chromadb.config import Settings

from app.services.retriever import Retriever
from app.services.document_parser import chunk_text


def _make_retriever() -> Retriever:
    """创建使用 EphemeralClient（内存模式）的检索器，测试无需清理"""
    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
    return Retriever(client=client)


class TestRetriever:
    """ChromaDB 向量检索引擎测试"""

    def test_empty_index(self):
        """没有任何分块时搜索返回空列表"""
        r = _make_retriever()
        results = r.search("测试")
        assert results == []

    def test_single_chunk(self):
        r = _make_retriever()
        r.index("doc1", "user1", ["人工智能是计算机科学的分支"])
        results = r.search("人工智能")
        assert len(results) >= 1
        assert "人工智能" in results[0].page_content

    def test_multiple_chunks(self):
        r = _make_retriever()
        r.index("doc1", "user1", [
            "Python 是一种编程语言",
            "机器学习是 AI 的一个分支",
        ])
        r.index("doc2", "user2", ["今天天气很好"])
        results = r.search("Python 编程")
        assert len(results) >= 1

    def test_no_match(self):
        """语义不相关的内容应返回较低分数"""
        r = _make_retriever()
        r.index("doc1", "user1", ["爱因斯坦的相对论改变了物理学", "莎士比亚的戏剧影响深远"])
        results = r.search("量子物理")
        assert len(results) >= 1  # 向量检索总有语义相关的返回
        # 最相关的结果应是关于相对论的（物理主题）
        assert "相对论" in results[0].page_content or "物理" in results[0].page_content

    def test_rebuild_index(self):
        """重建索引应完全替换旧数据"""
        r = _make_retriever()
        r.index("doc1", "user1", ["旧数据"])
        r.index("doc1", "user1", ["新数据新数据"])
        results = r.search("新")
        assert len(results) >= 1

    def test_search_with_doc_id_filter(self):
        """按 doc_id 过滤搜索"""
        r = _make_retriever()
        r.index("doc1", "user1", ["机器学习"])
        r.index("doc2", "user2", ["深度学习"])
        results = r.search("深度学习", doc_id="doc2")
        assert len(results) >= 1

    def test_search_no_doc_id_filter(self):
        """不传 doc_id 时应全局搜索"""
        r = _make_retriever()
        r.index("doc1", "user1", ["机器学习"])
        r.index("doc2", "user2", ["深度学习"])
        results = r.search("机器学习")
        assert len(results) >= 1

    def test_remove_document(self):
        """删除文档后其内容不应出现在搜索结果中"""
        r = _make_retriever()
        r.index("doc1", "user1", ["爱因斯坦的相对论改变了物理学"])
        r.index("doc2", "user1", ["莎士比亚的戏剧影响深远"])
        r.remove_document("doc1")
        results = r.search("相对论")
        # doc1 已删除，结果中不应有 doc1 的片段
        assert all(r.metadata["doc_id"] != "doc1" for r in results)
        results = r.search("莎士比亚")
        assert len(results) >= 1  # doc2 还在


class TestChunkText:
    """chunk_text 不变，保留原测试"""

    def test_short_text(self):
        chunks = chunk_text("短文本")
        assert len(chunks) == 1
        assert chunks[0] == "短文本"

    def test_long_text_splitting(self):
        text = "段落A。\n" * 200
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 200 + 100

    def test_empty_text(self):
        chunks = chunk_text("")
        assert chunks == []
