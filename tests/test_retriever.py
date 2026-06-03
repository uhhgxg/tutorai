"""TF-IDF 检索器测试（真实运行，scikit-learn 进程内）"""

import pytest

from app.services.retriever import Retriever
from app.services.document_parser import chunk_text


class TestRetriever:
    """TF-IDF 检索引擎测试"""

    def test_empty_index(self):
        """没有任何分块时搜索返回空列表"""
        r = Retriever()
        results = r.search("测试")
        assert results == []

    def test_single_chunk(self):
        r = Retriever()
        r.index([("doc1", "人工智能是计算机科学的分支")])
        results = r.search("人工智能")
        assert len(results) >= 1
        assert "人工智能" in results[0].page_content

    def test_multiple_chunks(self):
        r = Retriever()
        r.index([
            ("doc1", "Python 是一种编程语言"),
            ("doc1", "机器学习是 AI 的一个分支"),
            ("doc2", "今天天气很好"),
        ])
        results = r.search("Python 编程")
        assert len(results) >= 1

    def test_no_match(self):
        """低分结果应被过滤"""
        r = Retriever()
        r.index([("doc1", "人工智能基础"), ("doc1", "机器学习入门")])
        results = r.search("量子物理")
        assert len(results) == 0

    def test_rebuild_index(self):
        """重建索引应完全替换旧数据"""
        r = Retriever()
        r.index([("doc1", "旧数据")])
        r.index([("doc1", "新数据新数据")])
        results = r.search("新")
        assert len(results) >= 1

    def test_search_with_doc_id_filter(self):
        """按 doc_id 过滤搜索"""
        r = Retriever()
        r.index([("doc1", "机器学习"), ("doc2", "深度学习")])
        results = r.search("深度学习", doc_id="doc2")
        assert len(results) >= 1

    def test_search_no_doc_id_filter(self):
        """不传 doc_id 时应全局搜索"""
        r = Retriever()
        r.index([("doc1", "机器学习"), ("doc2", "深度学习")])
        results = r.search("机器学习")
        assert len(results) >= 1


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
