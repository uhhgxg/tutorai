"""聊天 API —— 对话管理 + 消息发送（流式）"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlite3 import Connection

from app.database import get_db, get_conversation, get_messages
from app.database import create_conversation as db_create_conv
from app.database import list_conversations as db_list_convs
from app.database import delete_conversation as db_delete_conv
from app.database import add_message, update_conversation_title
from app.models import ChatRequest, ConversationResponse, MessageResponse
from app.services.llm_client import chat_stream, chat, build_chat_messages
from app.auth import get_current_user

router = APIRouter(prefix="/api", tags=["chat"])


def get_conn():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    return db_list_convs(conn, user["id"])


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    title: str = "新对话",
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    return db_create_conv(conn, user["id"], title)


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    if not db_delete_conv(conn, conv_id):
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conv_id: str,
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    if not get_conversation(conn, conv_id):
        raise HTTPException(status_code=404, detail="对话不存在")
    return get_messages(conn, conv_id)


@router.post("/conversations/{conv_id}/messages")
def send_message(
    conv_id: str,
    req: ChatRequest,
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    """
    发送消息并流式返回 AI 回复
    
    处理流程：
    1. 验证对话是否存在
    2. 保存用户消息到数据库
    3. 如果是首条消息，自动生成对话标题
    4. 构建包含历史上下文的完整消息列表
    5. 调用 LLM 流式接口，逐 token 返回 AI 回复
    6. 流式传输结束后保存 AI 回复到数据库
    
    Args:
        conv_id (str): 对话ID
        req (ChatRequest): 聊天请求对象，包含用户发送的消息内容
        conn (Connection): 数据库连接对象，通过依赖注入自动提供
        
    Returns:
        StreamingResponse: 流式响应对象，以 text/plain 格式逐字返回 AI 回复
        
    Raises:
        HTTPException: 当对话不存在时抛出 404 错误
    """
    conv = get_conversation(conn, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 保存用户消息
    add_message(conn, conv_id, "user", req.message)

    # 如果是第一条消息，用其内容前 30 字作为对话标题
    history = get_messages(conn, conv_id)
    if len(history) == 1:
        title = req.message[:30] + ("..." if len(req.message) > 30 else "")
        update_conversation_title(conn, conv_id, title)

    # 构建消息列表
    msgs = build_chat_messages(
        [{"role": m["role"], "content": m["content"]} for m in history[:-1]],
        req.message,
    )

    full_response = []

    def generate():
        """
        生成器函数：逐 token 产生 AI 回复并在结束后保存到数据库
        
        Yields:
            str: AI 回复的每个 token
        """
        for token in chat_stream(msgs):
            full_response.append(token)
            yield token
        # 流结束后保存 AI 回复
        add_message(conn, conv_id, "assistant", "".join(full_response))

    return StreamingResponse(generate(), media_type="text/plain")


@router.post("/conversations/{conv_id}/messages/sync")
def send_message_sync(
    conv_id: str,
    req: ChatRequest,
    conn: Connection = Depends(get_conn),
    user: dict = Depends(get_current_user),
):
    """
    发送消息并同步返回完整的 AI 回复
    
    处理流程：
    1. 验证对话是否存在
    2. 保存用户消息到数据库
    3. 如果是首条消息，自动生成对话标题
    4. 构建包含历史上下文的完整消息列表
    5. 调用 LLM 同步接口，等待完整回复
    6. 保存 AI 回复到数据库并一次性返回
    
    Args:
        conv_id (str): 对话ID
        req (ChatRequest): 聊天请求对象，包含用户发送的消息内容
        conn (Connection): 数据库连接对象，通过依赖注入自动提供
        
    Returns:
        dict: 包含完整 AI 回复的字典，格式为 {"reply": str}
        
    Raises:
        HTTPException: 当对话不存在时抛出 404 错误
    """
    conv = get_conversation(conn, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    add_message(conn, conv_id, "user", req.message)

    history = get_messages(conn, conv_id)
    if len(history) == 1:
        title = req.message[:30] + ("..." if len(req.message) > 30 else "")
        update_conversation_title(conn, conv_id, title)

    msgs = build_chat_messages(
        [{"role": m["role"], "content": m["content"]} for m in history[:-1]],
        req.message,
    )

    reply = chat(msgs)
    add_message(conn, conv_id, "assistant", reply)
    return {"reply": reply}
