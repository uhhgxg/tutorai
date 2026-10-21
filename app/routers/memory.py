"""记忆 API —— 查看、添加和删除用户自己的学习记忆。"""

from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.db.engine import get_db
from app.db.memory_repo import delete_memory, list_memories, save_memory
from app.models import MemoryCreateRequest, MemoryResponse

router = APIRouter(prefix="/api/memories", tags=["memory"])


@router.get("", response_model=list[MemoryResponse])
def get_memories(
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    return list_memories(conn, user["id"], limit=50)


@router.post("", response_model=MemoryResponse)
def create_memory(
    req: MemoryCreateRequest,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        return save_memory(conn, user["id"], req.content, req.category, source="api")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{memory_id}")
def remove_memory(
    memory_id: str,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if not delete_memory(conn, user["id"], memory_id):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"ok": True}
