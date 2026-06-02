"""TF-IDF 检索器测试 —— 基于 LangChain TFIDFRetriever"""

from app.services.retriever import Retriever
from app.services.document_parser import chunk_text


class TestRetriever:
    def test_empty_index(self):
        r = Retriever()
        results = r.search("测试")
        assert results == []

    def test_single_chunk(self):
        r = Retriever()
        r.index(["人工智能是计算机科学的分支"])
        results = r.search("人工智能")
        assert len(results) == 1
        assert "人工智能" in results[0].page_content

    def test_multiple_chunks(self):
        r = Retriever()
        r.index([
            "Python 是一种编程语言",
            "机器学习是 AI 的一个分支",
            "今天天气很好",
        ])
        results = r.search("Python 编程")
        assert len(results) >= 1
        assert "Python" in results[0].page_content

    def test_no_match(self):
        r = Retriever()
        r.index(["人工智能基础", "机器学习入门"])
        results = r.search("量子物理")
        # 低分结果被 0.01 阈值过滤
        assert len(results) == 0

    def test_rebuild_index(self):
        r = Retriever()
        r.index(["旧数据"])
        r.index(["新数据新数据"])
        results = r.search("新")
        assert len(results) == 1
        assert "新数据" in results[0].page_content


class TestChunkText:
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
