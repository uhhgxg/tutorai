"""文档解析 —— 支持 PDF / TXT / Markdown / 代码文件 / 扫描件 OCR

基于 LangChain RecursiveCharacterTextSplitter 进行智能分块。
PDF 解析策略：
  1. 优先提取文本层（适用于电子版 PDF）
  2. 当文本提取结果稀疏时，自动降级到 OCR（适用于扫描件/图片 PDF）
"""

import logging

import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# OCR 每页最小文本阈值（字符数）—— 低于此值则对该页运行 OCR
_OCR_TEXT_THRESHOLD = 30


def parse_pdf(file_bytes: bytes) -> str:
    """从 PDF 二进制中提取纯文本，图片 PDF 自动降级到 OCR"""
    text_parts: list[str] = []
    ocr_pages: list[tuple[int, bytes]] = []  # (page_number, png_bytes)

    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                text_parts.append(text)

            # 文本过少 → 渲染为图片，稍后统一 OCR
            if len(text.strip()) < _OCR_TEXT_THRESHOLD:
                # 300 DPI 渲染，确保 OCR 准确率
                pix = page.get_pixmap(dpi=300)
                ocr_pages.append((page_num, pix.tobytes("png")))

    # 对有图片内容的页面运行 OCR
    if ocr_pages:
        ocr_text = _ocr_fallback(ocr_pages)
        if ocr_text.strip():
            text_parts.append(ocr_text)

    return "\n\n".join(text_parts)


def _ocr_fallback(image_pages: list[tuple[int, bytes]]) -> str:
    """对图片页运行 OCR（pytesseract），支持中英文混合"""
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        logger.warning("pytesseract 或 Pillow 未安装，跳过 OCR 降级")
        return ""

    # 检查 tesseract 是否可用
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        logger.warning("系统未安装 tesseract-ocr，跳过 OCR 降级")
        return ""

    parts: list[str] = []
    for page_num, img_data in image_pages:
        try:
            image = Image.open(io.BytesIO(img_data))
            # 中英文混合识别
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            if text.strip():
                logger.info("OCR 成功识别第 %d 页 (%d 字符)", page_num + 1, len(text.strip()))
                parts.append(text)
            else:
                logger.info("OCR 第 %d 页未识别到内容", page_num + 1)
        except Exception as exc:
            logger.error("OCR 第 %d 页失败: %s", page_num + 1, exc)

    return "\n\n".join(parts)


def parse_text(file_bytes: bytes) -> str:
    """解析纯文本文件"""
    return file_bytes.decode("utf-8", errors="replace")


def parse_document(filename: str, file_bytes: bytes) -> str:
    """根据文件扩展名选择解析器，返回文本内容"""
    name = filename.lower()

    if name.endswith(".pdf"):
        return parse_pdf(file_bytes)
    elif name.endswith(
        (".txt", ".md", ".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml")
    ):
        return parse_text(file_bytes)
    else:
        raise ValueError(f"不支持的文件格式: {filename}")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """将长文本拆分为重叠的分块，支持中英文句子边界"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=[
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            ".",
            "!",
            "?",
            "；",
            ";",
            " ",
            "",
        ],
    )
    chunks = [c for c in splitter.split_text(text) if c.strip()]
    return chunks if chunks else ([text.strip()[:chunk_size]] if text.strip() else [])
