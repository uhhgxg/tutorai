"""聊天服务 —— 对话管理 + Agent 编排"""

import logging
from sqlite3 import Connection

from fastapi import HTTPException

from app.agent import ToolRegistry, TurnContext, TutorOrchestrator
from app.config import settings
from app.db.conversation_repo import (
    add_message as repo_add_msg,
)
from app.db.conversation_repo import (
    create_conversation as repo_create_conv,
)
from app.db.conversation_repo import (
    delete_conversation as repo_delete_conv,
)
from app.db.conversation_repo import (
    get_conversation as repo_get_conv,
)
from app.db.conversation_repo import (
    get_messages as repo_get_msgs,
)
from app.db.conversation_repo import (
    list_conversations as repo_list_convs,
)
from app.db.conversation_repo import (
    update_conversation_title as repo_update_title,
)
from app.db.engine import get_db_connection
from app.db.memory_repo import list_memories
from app.services.llm_client import LLMError, build_chat_messages
from app.services.tools import create_user_tools

logger = logging.getLogger(__name__)


class ChatService:
    """聊天服务，每个请求实例绑定一个 user_id"""

    def __init__(self, user_id: str):
        self._user_id = user_id
        self._tool_registry = ToolRegistry(create_user_tools(user_id))
        self._orchestrator = TutorOrchestrator()

    # --- 对话管理 ---

    def create_conversation(self, conn: Connection, title: str = "新对话") -> dict:
        return repo_create_conv(conn, self._user_id, title)

    def list_conversations(self, conn: Connection) -> list[dict]:
        return repo_list_convs(conn, self._user_id)

    def delete_conversation(self, conn: Connection, conv_id: str) -> bool:
        return repo_delete_conv(conn, conv_id, self._user_id)

    def get_conversation(self, conn: Connection, conv_id: str) -> dict | None:
        return repo_get_conv(conn, conv_id, self._user_id)

    # --- 消息 ---

    def get_messages(self, conn: Connection, conv_id: str) -> list[dict]:
        return repo_get_msgs(conn, conv_id, self._user_id)

    def _prepare_chat(self, conn: Connection, conv_id: str, message: str):
        """验证对话、保存消息、构建历史，并组装一次 Agent TurnContext。"""
        conv = repo_get_conv(conn, conv_id, self._user_id)
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")

        repo_add_msg(conn, conv_id, self._user_id, "user", message)
        history = repo_get_msgs(conn, conv_id, self._user_id, limit=20)

        if len(history) == 1:
            title = message[:30] + ("..." if len(message) > 30 else "")
            repo_update_title(conn, conv_id, self._user_id, title)

        memory_context = "\n".join(
            f"- [{memory['category']}] {memory['content']}"
            for memory in list_memories(conn, self._user_id, limit=settings.max_memory_items)
        )

        messages = build_chat_messages(
            [{"role": m["role"], "content": m["content"]} for m in history[:-1]],
            message,
            memory_context=memory_context,
        )
        return TurnContext(
            user_id=self._user_id,
            conversation_id=conv_id,
            user_message=message,
            messages=messages,
            tools=self._tool_registry,
        )

    def send_message_stream(self, conn: Connection, conv_id: str, message: str):
        """流式发送消息（返回 generator，由 router 包装为 StreamingResponse）"""
        context = self._prepare_chat(conn, conv_id, message)
        full_response: list[str] = []

        def generate():
            try:
                for token in self._orchestrator.stream_text(context):
                    full_response.append(token)
                    yield token
            except GeneratorExit:
                pass
            finally:
                if full_response:
                    self._save_assistant_message(conv_id, "".join(full_response))

        return generate()

    async def send_message_sync(self, conn: Connection, conv_id: str, message: str) -> dict:
        """异步发送消息（非流式）—— 通过 asyncio.to_thread 避免阻塞事件循环"""
        context = self._prepare_chat(conn, conv_id, message)
        try:
            reply = (await self._orchestrator.run_async(context)).reply
        except LLMError as e:
            raise HTTPException(status_code=503, detail=str(e))
        self._save_assistant_message(conv_id, reply)
        return {"reply": reply}

    def _save_assistant_message(self, conv_id: str, content: str) -> None:
        """独立 DB 连接保存 assistant 消息，避免请求作用域 conn 已关闭"""
        if not content:
            return
        try:
            db = get_db_connection()
            try:
                repo_add_msg(db, conv_id, self._user_id, "assistant", content)
            finally:
                db.close()
        except Exception as e:
            logger.warning("保存 assistant 消息失败（客户端可能已断开）: %s", e)
