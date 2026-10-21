"""出题服务 —— 练习题生成和结果管理"""

import logging
from sqlite3 import Connection

from fastapi import HTTPException

from app.db.quiz_repo import (
    delete_quiz_result as repo_delete_result,
)
from app.db.quiz_repo import (
    get_quiz_result as repo_get_result,
)
from app.db.quiz_repo import (
    list_quiz_results as repo_list_results,
)
from app.db.quiz_repo import (
    save_quiz_result as repo_save_result,
)
from app.services.document_parser import parse_document
from app.services.llm_client import build_quiz_messages, chat_stream
from app.services.retriever import search_chunks

logger = logging.getLogger(__name__)


class QuizService:
    """出题服务，每个请求实例绑定一个 user_id"""

    def __init__(self, user_id: str):
        self._user_id = user_id

    def generate(self, content: str, question_count: int, question_type: str):
        """根据文本生成练习题（返回 generator）"""
        messages = build_quiz_messages(content, question_count, question_type)
        return chat_stream(messages, temperature=0.8, max_tokens=3000)

    def generate_from_kb(self, topic: str, doc_id: str | None, question_count: int, question_type: str):
        """从知识库检索知识点并生成练习题（返回 generator）"""
        results = search_chunks(topic, top_k=5, doc_id=doc_id, user_id=self._user_id)
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"未找到与「{topic}」相关的文档内容，请先上传相关教材。",
            )

        content = "\n\n".join([doc.page_content for doc in results])
        messages = build_quiz_messages(content, question_count, question_type)
        return chat_stream(messages, temperature=0.8, max_tokens=3000)

    async def generate_from_file(self, file, question_count: int, question_type: str):
        """上传文档并生成练习题（返回 generator）"""
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        raw_bytes = await file.read()

        try:
            content = parse_document(file.filename, raw_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not content.strip():
            raise HTTPException(status_code=400, detail="文档内容为空")

        content = content[:4000]
        messages = build_quiz_messages(content, question_count, question_type)
        return chat_stream(messages, temperature=0.8, max_tokens=3000)

    # --- 结果管理 ---

    def save_result(self, conn: Connection, title: str, result_text: str, question_count: int | None = None) -> dict:
        return repo_save_result(conn, self._user_id, title, result_text, question_count)

    def list_results(self, conn: Connection) -> list[dict]:
        return repo_list_results(conn, self._user_id)

    def get_result(self, conn: Connection, result_id: str) -> dict | None:
        return repo_get_result(conn, self._user_id, result_id)

    def delete_result(self, conn: Connection, result_id: str) -> bool:
        return repo_delete_result(conn, self._user_id, result_id)
