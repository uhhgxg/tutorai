"""
【RAG核心】文档 API —— 上传、列表、查询、删除
"""
# ↑ RAG 链路的入口大门：接收用户上传的文件，协调解析器、检索器、LLM 完成问答
# RAG 链路：步骤① 上传文件 / 步骤⑥⑦ 拼接上下文+LLM生成+流式返回

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
# ↑ APIRouter: 创建路由分组 / Depends: 依赖注入（自动传入数据库连接）
# UploadFile: FastAPI 专门处理文件上传的类型

from sqlite3 import Connection  # Python 内置的 SQLite 数据库连接对象

# ── 数据库操作 ──
from app.database import get_db, list_documents, get_document_chunks
from app.database import save_document as db_save_doc
from app.database import delete_document as db_delete_doc
from app.database import get_all_chunks
from app.auth import get_current_user
# ── 数据模型（Pydantic 校验） ──
from app.models import DocumentResponse, DocumentQueryRequest, DocumentQueryResponse
# ↑ DocumentQueryRequest: 前端发来的查询请求格式（question + top_k + doc_id）
# ── 业务服务 ──
from app.services.document_parser import parse_document, chunk_text
# ↑ parse_document: 根据文件后缀自动选择解析器（PDF→PyMuPDF/OCR，TXT→直接读）
# chunk_text: 把长文本递归切成小段
from app.services.retriever import get_retriever, rebuild_index
# ↑ get_retriever: 获取全局唯一的 TF-IDF 检索引擎实例
# rebuild_index: 上传/删除文档后重建 TF-IDF 索引
from app.services.llm_client import chat  # 调用大模型（非流式），一次返回完整回答

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
        # 文件内容全是空白（比如空 PDF），返回 400
        raise HTTPException(status_code=400, detail="文档内容为空")

    # 把长文本切分成小段落（chunks）
    # chunk_size 和 overlap 在 app/config.py 里配置
    chunks = chunk_text(content)

    # 存入 SQLite：同时写入 documents 表和 chunks 表
    doc = db_save_doc(conn, user["id"], file.filename, content, chunks)

    # ── 关键步骤：重建全局 TF-IDF 索引 ──
    # 为什么上传一个文件要重建"全局"索引？
    # 因为 TF-IDF 的权重是相对于所有文档计算的，
    # 每新增/删除一篇文档，每个词的"重要性"都会变
    all_chunks = get_all_chunks(conn)  # 读出库里所有文档的所有切片
    rebuild_index(all_chunks)  # 重新训练 TF-IDF + 替换内存中的向量矩阵

    return doc  # 返回新创建的文档信息


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    if not db_delete_doc(conn, user["id"], doc_id):
        # 如果 doc_id 不存在，返回 404
        raise HTTPException(status_code=404, detail="文档不存在")

    # 删除后同样要重建 TF-IDF 索引（权重变了）
    all_chunks = get_all_chunks(conn)
    rebuild_index(all_chunks)
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
        raise HTTPException(status_code=404, detail="文档不存在或内容为空")

    # ── RAG 核心：TF-IDF 向量检索 ──
    retriever = get_retriever()  # 获取全局单例检索器
    results = retriever.search(req.question, top_k=req.top_k, doc_id=doc_id)
    # ↑ 把问题转向量 → 和库里该文档的所有切片算余弦相似度 → 返回 top_k 段

    if not results:
        # 没找到相关内容，直接返回"未找到"
        return DocumentQueryResponse(answer="未找到与问题相关的内容。", sources=[])

    # ── 拼接上下文 ──
    # 把检索到的段落拼成一段文字（每段最多取 800 字，防止 token 超限）
    context = "\n\n".join([doc.page_content[:800] for doc in results])
    # 同时准备引用来源（每段取前 200 字作为摘要返给前端展示）
    sources = [doc.page_content[:200] + ("..." if len(doc.page_content) > 200 else "") for doc in results]

    # ── 组装 prompt，调大模型 ──
    messages = [
        {
            "role": "system",
            "content": "你是文档分析助手。仅根据提供的文档内容回答问题。如果文档中没有相关信息，如实说明。用中文回答。",
        },
        # ↑ 系统提示词：约束 AI 只基于文档回答，禁止瞎编
        {
            "role": "user",
            "content": f"文档内容:\n{context[:4000]}\n\n问题: {req.question}",
        },
        # ↑ 用户消息：检索到的段落（最多 4000 字） + 用户问题
    ]

    # 调用大模型生成回答（非流式，一次返回完整结果）
    answer = chat(messages)

    # 返回回答 + 引用来源
    return DocumentQueryResponse(answer=answer, sources=sources)
