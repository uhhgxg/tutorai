"""文档解析器测试"""

import pytest
from app.services.document_parser import parse_document, parse_text


class TestParseText:
    def test_utf8_text(self):
        result = parse_text("Hello World".encode("utf-8"))
        assert result == "Hello World"

    def test_chinese_text(self):
        result = parse_text("人工智能基础".encode("utf-8"))
        assert result == "人工智能基础"


class TestParseDocument:
    def test_txt_file(self):
        result = parse_document("test.txt", "这是文本内容".encode("utf-8"))
        assert result == "这是文本内容"

    def test_md_file(self):
        result = parse_document("readme.md", "# 标题\n内容".encode("utf-8"))
        assert "标题" in result

    def test_py_file(self):
        result = parse_document("app.py", b'print("hello")')
        assert 'print("hello")' in result

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="不支持的文件格式"):
            parse_document("test.xyz", b"data")
