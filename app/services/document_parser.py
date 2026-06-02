"""文档解析 —— 支持 PDF / TXT / Markdown / 代码文件

基于 LangChain RecursiveCharacterTextSplitter 进行智能分块。
"""

import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter


def parse_pdf(file_bytes: bytes) -> str:
    """从 PDF 二进制中提取纯文本"""
    parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            if text.strip():
                parts.append(text)
    return "\n\n".join(parts)


def parse_text(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace")


def parse_document(filename: str, file_bytes: bytes) -> str:
    """根据文件扩展名选择解析器，返回文本内容"""
    name = filename.lower()

    if name.endswith(".pdf"):
        return parse_pdf(file_bytes)
    elif name.endswith((".txt", ".md", ".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml")):
        return parse_text(file_bytes)
    else:
        raise ValueError(f"不支持的文件格式: {filename}")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """将长文本拆分为重叠的分块，支持中英文句子边界"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", " ", ""],
    )
    chunks = [c for c in splitter.split_text(text) if c.strip()]
    return chunks if chunks else ([text.strip()[:chunk_size]] if text.strip() else [])
