"""文档 API —— 上传、列表、查询、删除"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlite3 import Connection

from app.database import get_db, list_documents, get_document_chunks
from app.database import save_document as db_save_doc
from app.database import delete_document as db_delete_doc
from app.database import get_all_chunks
from app.models import DocumentResponse, DocumentQueryRequest, DocumentQueryResponse
from app.services.document_parser import parse_document, chunk_text
from app.services.retriever import get_retriever, rebuild_index
from app.services.llm_client import chat

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_conn():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


@router.get("", response_model=list[DocumentResponse])
def list_docs(conn: Connection = Depends(get_conn)):
    return list_documents(conn)


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...), conn: Connection = Depends(get_conn)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    try:
        content = parse_document(file.filename, await file.read())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not content.strip():
        raise HTTPException(status_code=400, detail="文档内容为空")

    chunks = chunk_text(content)
    doc = db_save_doc(conn, file.filename, content, chunks)

    # 重建全局索引
    all_chunks = get_all_chunks(conn)
    rebuild_index(all_chunks)

    return doc


@router.delete("/{doc_id}")
def delete_document(doc_id: str, conn: Connection = Depends(get_conn)):
    if not db_delete_doc(conn, doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    # 重建索引
    all_chunks = get_all_chunks(conn)
    rebuild_index(all_chunks)
    return {"ok": True}


@router.post("/{doc_id}/query", response_model=DocumentQueryResponse)
def query_document(doc_id: str, req: DocumentQueryRequest, conn: Connection = Depends(get_conn)):
    chunks = get_document_chunks(conn, doc_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="文档不存在或内容为空")

    # TF-IDF 向量搜索（指定 doc_id 过滤，无需重建临时索引）
    retriever = get_retriever()
    results = retriever.search(req.question, top_k=req.top_k, doc_id=doc_id)

    if not results:
        return DocumentQueryResponse(answer="未找到与问题相关的内容。", sources=[])

    context = "\n\n".join([doc.page_content[:800] for doc in results])
    sources = [doc.page_content[:200] + ("..." if len(doc.page_content) > 200 else "") for doc in results]

    messages = [
        {
            "role": "system",
            "content": "你是文档分析助手。仅根据提供的文档内容回答问题。如果文档中没有相关信息，如实说明。用中文回答。",
        },
        {
            "role": "user",
            "content": f"文档内容:\n{context[:4000]}\n\n问题: {req.question}",
        },
    ]

    answer = chat(messages)
    return DocumentQueryResponse(answer=answer, sources=sources)
