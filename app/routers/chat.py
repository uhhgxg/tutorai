"""聊天 API —— 对话管理 + 消息发送（流式）"""

import logging
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.db.engine import get_db
from app.models import ChatRequest, ConversationResponse, MessageResponse
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = ChatService(user["id"])
    return svc.list_conversations(conn)


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    title: str = "新对话",
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = ChatService(user["id"])
    return svc.create_conversation(conn, title)


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = ChatService(user["id"])
    if not svc.delete_conversation(conn, conv_id):
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conv_id: str,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = ChatService(user["id"])
    if not svc.get_conversation(conn, conv_id):
        raise HTTPException(status_code=404, detail="对话不存在")
    return svc.get_messages(conn, conv_id)


@router.post("/conversations/{conv_id}/messages")
def send_message(
    conv_id: str,
    req: ChatRequest,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """流式发送消息；客户端断开时仍尽力保存已生成的回复"""
    svc = ChatService(user["id"])
    return StreamingResponse(
        svc.send_message_stream(conn, conv_id, req.message),
        media_type="text/plain",
    )


@router.post("/conversations/{conv_id}/messages/sync")
async def send_message_sync(
    conv_id: str,
    req: ChatRequest,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """发送消息并同步返回完整的 AI 回复"""
    svc = ChatService(user["id"])
    return await svc.send_message_sync(conn, conv_id, req.message)
