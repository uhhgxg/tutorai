"""
【RAG核心】文档解析模块 —— 负责读取用户上传的文件，把内容变成纯文本

📌 大白话：这个文件就像是项目的"阅读器"和"切纸机"。
  - 「阅读器」：不管用户传的是 PDF 还是 TXT，它都能把文字读出来
  - 「切纸机」：把长篇大论切成合适的小段，方便后续检索

支持的文件格式：
  - PDF（电子版优先提取文字，扫描版自动调用 OCR 识别）
  - TXT、Markdown、Python/JS 等代码文件
  - 图片型 PDF 自动降级到 OCR 识别（需要安装 tesseract）

基于 LangChain RecursiveCharacterTextSplitter 进行智能分块。
PDF 解析策略：
  1. 优先提取文本层（适用于电子版 PDF）
  2. 当文本提取结果稀疏时，自动降级到 OCR（适用于扫描件/图片 PDF）
"""

import logging
import os

import fitz  # PyMuPDF —— Python 最流行的 PDF 处理库，免费开源
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

# 日志记录器：记录程序运行过程中的重要信息，方便排查问题
logger = logging.getLogger(__name__)

# OCR 每页最小文本阈值（字符数）
# 如果某页 PDF 提取到的文字少于 30 个字，就认为这页是「扫描件/图片」
# 程序会自动对该页截图，然后用 OCR 识别图片中的文字
_OCR_TEXT_THRESHOLD = 30


def parse_pdf(file_bytes: bytes) -> str:
    """
    从 PDF 二进制中提取纯文本，图片 PDF 自动降级到 OCR

    怎么工作的？
    1. 用 PyMuPDF 打开 PDF 文件
    2. 逐页检查：这一页是文字版还是图片版？
       - 文字版：直接用 get_text() 提取文字（又快又准）
       - 图片版：文字太少（<30字）→ 渲染成图片 → 调 OCR 识别
    3. 把所有页面提取到的文字拼在一起返回
    """
    text_parts: list[str] = []
    ocr_pages: list[tuple[int, bytes]] = []  # (page_number, png_bytes)

    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc):
            # get_text()：提取 PDF 页面的文字层内容
            # 电子版 PDF 有文字层，可以直接提取
            text = page.get_text()
            if text.strip():
                text_parts.append(text)

            # 文本过少 → 渲染为图片，稍后统一 OCR
            # 说明这页是扫描件/图片（文字被"印"在图片上）
            if len(text.strip()) < _OCR_TEXT_THRESHOLD:
                # 300 DPI 渲染，确保 OCR 准确率
                # DPI 越高图片越清晰，OCR 识别越准
                pix = page.get_pixmap(dpi=300)
                ocr_pages.append((page_num, pix.tobytes("png")))

    # 对有图片内容的页面运行 OCR
    if ocr_pages:
        ocr_text = _ocr_fallback(ocr_pages)
        if ocr_text.strip():
            text_parts.append(ocr_text)

    return "\n\n".join(text_parts)


def _ocr_fallback(image_pages: list[tuple[int, bytes]]) -> str:
    """
    OCR 降级方案 —— 当 PDF 是扫描件（图片）时，用文字识别提取内容

    📌 大白话：
    有些 PDF 其实是「照片集」（比如用手机拍的书页），里面没有真正的文字。
    这时候就要用 OCR（光学字符识别）技术，「看」图片里的文字长什么样。

    需要安装：
    - pip install pytesseract Pillow
    - 系统安装 tesseract-ocr（https://github.com/UB-Mannheim/tesseract/wiki）
    """
    try:
        import pytesseract  # Google 的 OCR 引擎 Python 封装
        from PIL import Image  # Python 图片处理库
        import io
    except ImportError:
        logger.warning("pytesseract 或 Pillow 未安装，跳过 OCR 降级")
        return ""

    # 配置 Tesseract 路径（默认安装路径）
    tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    # 配置 TESSDATA_PREFIX（中文语言包路径）
    tessdata_prefix = r"D:\tesseract\tessdata"
    if settings.tessdata_prefix and os.path.exists(settings.tessdata_prefix):
        tessdata_prefix = settings.tessdata_prefix
    os.environ["TESSDATA_PREFIX"] = tessdata_prefix

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
            # 中英文混合识别（chi_sim=简体中文, eng=英文）
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
    """
    解析纯文本文件

    纯文本（.txt / .md / .py 等）本来就包含文字，
    不需要 OCR，直接按 UTF-8 编码读取就行。
    errors="replace" 意思是：如果遇到无法解码的字符，用 � 代替，不中断程序。
    """
    return file_bytes.decode("utf-8", errors="replace")


def parse_document(filename: str, file_bytes: bytes) -> str:
    """
    【入口函数】根据文件后缀名，自动选择解析方式

    这是 document_parser 模块的「总调度」函数：
    - 传 PDF → 调 parse_pdf（判断是文字版还是扫描件，自动处理）
    - 传 TXT/MD/PY 等文本 → 直接 decode 读取
    - 其他格式 → 报错提示不支持

    📌 在 RAG 链路中的位置：步骤②「读取文档」
    上游：document.py（接收用户上传）
    下游：chunk_text()（把读出来的内容切分）
    """
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
    """
    【核心函数】将长文本拆分为多个小段落（chunks）

    📌 为什么需要切分？
    大模型每次能处理的内容有限（就像人一次记不住整本书），
    所以要把长篇文档切成合适大小的小段，检索时只拿最相关的几段去问 AI。

    切分策略（递归字符切分，按优先级依次尝试）：
    1. 先在「双换行」处切（段落边界）—— 最自然，优先保留段落完整
    2. 段落还太长 → 在「单换行」处切
    3. 还太长 → 在「句号」处切（中文句子边界）
    4. 还太长 → 在「空格」处切（英文单词边界）
    5. 最后手段 → 硬切（按字符数）

    chunk_overlap（重叠）：相邻两段有 50 字重叠，
    避免在句子中间切断导致丢失关键信息。
    就像拼图一样，两块之间留一点重叠区域保证能拼上。

    参数可在 app/config.py 中配置：
    - CHUNK_SIZE：每段目标字数（默认 500）
    - CHUNK_OVERLAP：相邻重叠字数（默认 50）

    📌 在 RAG 链路中的位置：步骤③「文本切分」
    上游：parse_document()（已读取的原始文本）
    下游：retriever.py 的 build_index()（对切块建 TF-IDF 索引）
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=[
            "\n\n",  # 首选：段落边界（双换行）
            "\n",    # 其次：行边界（单换行）
            "。",    # 中文句号
            "！",    # 中文感叹号
            "？",    # 中文问号
            ".",     # 英文句号
            "!",     # 英文感叹号
            "?",     # 英文问号
            "；",    # 中文分号
            ";",     # 英文分号
            " ",     # 空格（英文单词边界）
            "",      # 最后：按字符硬切
        ],
    )
    chunks = [c for c in splitter.split_text(text) if c.strip()]
    return chunks if chunks else ([text.strip()[:chunk_size]] if text.strip() else [])
