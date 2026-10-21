"""文档 API —— 上传、列表、查询、删除"""

from sqlite3 import Connection

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth import get_current_user
from app.db.engine import get_db
from app.models import DocumentQueryRequest, DocumentQueryResponse, DocumentResponse
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentResponse])
def list_docs(
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = DocumentService(user["id"])
    return svc.list_documents(conn)


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = DocumentService(user["id"])
    return await svc.upload(file, conn)


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = DocumentService(user["id"])
    if not svc.delete_document(conn, doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"ok": True}


@router.post("/{doc_id}/query", response_model=DocumentQueryResponse)
async def query_document(
    doc_id: str,
    req: DocumentQueryRequest,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = DocumentService(user["id"])
    return await svc.query_document(conn, doc_id, req.question, top_k=req.top_k)
