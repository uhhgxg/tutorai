"""
【RAG核心】文档 API —— 上传、列表、查询、删除
"""
# ↑ RAG 链路的入口大门：接收用户上传的文件，协调解析器、检索器、LLM 完成问答
# RAG 链路：步骤① 上传文件 / 步骤⑥⑦ 拼接上下文+LLM生成+流式返回

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
# ↑ APIRouter: 创建路由分组 / Depends: 依赖注入（自动传入数据库连接）
# UploadFile: FastAPI 专门处理文件上传的类型

import asyncio

from sqlite3 import Connection  # Python 内置的 SQLite 数据库连接对象

# ── 数据库操作 ──
from app.database import get_db, list_documents, get_document_chunks
from app.database import save_document as db_save_doc
from app.database import delete_document as db_delete_doc
from app.auth import get_current_user
# ── 数据模型（Pydantic 校验） ──
from app.models import DocumentResponse, DocumentQueryRequest, DocumentQueryResponse
# ↑ DocumentQueryRequest: 前端发来的查询请求格式（question + top_k + doc_id）
# ── 业务服务 ──
from app.services.document_parser import parse_document, chunk_text
from app.services.retriever import get_retriever
from app.services.llm_client import chat, agent_chat, LLMError
from app.services.tools import AGENT_TOOLS

# 创建路由分组，所有接口前面自动加 /api/documents
router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_conn():
    """获取 SQLite 数据库连接（FastAPI 自动管理，用完自动关闭）"""
    # ↑ 这是一个依赖项（Dependency），FastAPI 会在请求处理完后自动调用 finally
    conn = get_db()  # 从连接池拿一个数据库连接
    try:
        yield conn  # 把连接交给路由函数使用
    finally:
        conn.close()  # 请求结束后自动归还/关闭连接


@router.get("", response_model=list[DocumentResponse])
def list_docs(
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    return list_documents(conn, user["id"])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    # File(...) 表示这是一个必须上传的文件字段
    # UploadFile 自动处理文件流，支持大文件

    if not file.filename:
        # 如果前端没传文件名，返回 400 错误
        raise HTTPException(status_code=400, detail="文件名不能为空")

    try:
        # 调用解析器读取文件内容，返回纯文本
        # parse_document 内部根据后缀自动分流：PDF→PyMuPDF，TXT→直接读
        content = parse_document(file.filename, await file.read())
    except ValueError as e:
        # 传了不支持的文件格式（比如 .exe），抛 ValueError
        raise HTTPException(status_code=400, detail=str(e))

    if not content.strip():
        raise HTTPException(status_code=400, detail="文档内容为空")

    # 分块 + 向量化（同步操作，使用线程池避免阻塞事件循环）
    chunks = await asyncio.to_thread(chunk_text, content)

    # 存入 SQLite
    doc = db_save_doc(conn, user["id"], file.filename, content, chunks)

    # ── 关键步骤：写入向量索引 ──
    # ChromaDB 增量添加，无需重建全局索引
    await asyncio.to_thread(get_retriever().index, doc["id"], user["id"], chunks)

    return doc  # 返回新创建的文档信息


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    if not db_delete_doc(conn, user["id"], doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")

    get_retriever().remove_document(doc_id)
    return {"ok": True}  # 返回成功标记


@router.post("/{doc_id}/query", response_model=DocumentQueryResponse)
def query_document(
    doc_id: str,
    req: DocumentQueryRequest,
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    # 先检查文档是否存在（仅限当前用户的文档）
    chunks = get_document_chunks(conn, user["id"], doc_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="文档不存在")

    # ---- Agent 让 LLM 自主调用 retrieve_document 检索 ----
    system_prompt = (
        "你是文档问答助手。请调用 retrieve_document 工具来检索文档内容并回答用户问题。\n"
        f"当前文档 ID 是: {doc_id}，"
        "请将 doc_id 参数传给 retrieve_document 工具。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.question},
    ]

    # Agent 让 LLM 自主调用工具检索文档生成答案
    try:
        answer = agent_chat(messages, tools=AGENT_TOOLS)
    except LLMError as e:
        answer = f"⚠️ {e}"

    # ---- 同时用 ChromaDB 检索相关段落作为补充来源 ----
    results = get_retriever().search(req.question, top_k=req.top_k, doc_id=doc_id)
    sources = [
        doc.page_content[:200] + ("..." if len(doc.page_content) > 200 else "")
        for doc in results
    ]

    return DocumentQueryResponse(answer=answer, sources=sources)
