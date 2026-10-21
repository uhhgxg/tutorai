"""文档服务 —— 上传、检索、RAG 问答"""

import asyncio
import logging
from sqlite3 import Connection

from fastapi import HTTPException

from app.config import settings
from app.db.document_repo import (
    delete_document as repo_delete_doc,
)
from app.db.document_repo import (
    get_document_chunks as repo_get_chunks,
)
from app.db.document_repo import (
    list_documents as repo_list_docs,
)
from app.db.document_repo import (
    save_document as repo_save_doc,
)
from app.services.document_parser import chunk_text, parse_document
from app.services.llm_client import LLMError, chat_async
from app.services.retriever import get_retriever

logger = logging.getLogger(__name__)


class DocumentService:
    """文档服务，每个请求实例绑定一个 user_id"""

    def __init__(self, user_id: str):
        self._user_id = user_id

    def list_documents(self, conn: Connection) -> list[dict]:
        return repo_list_docs(conn, self._user_id)

    def delete_document(self, conn: Connection, doc_id: str) -> bool:
        deleted = repo_delete_doc(conn, self._user_id, doc_id)
        if deleted:
            get_retriever().remove_document(doc_id)
        return deleted

    def get_chunks(self, conn: Connection, doc_id: str) -> list[str]:
        return repo_get_chunks(conn, self._user_id, doc_id)

    async def upload(self, file, conn: Connection) -> dict:
        """上传文档：读取 → 解析 → 分块 → 入库 → 建向量索引"""
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        raw_bytes = await file.read()
        if len(raw_bytes) > settings.max_upload_size:
            max_mb = settings.max_upload_size // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"文件大小超过限制（最大 {max_mb}MB）",
            )

        try:
            content = await asyncio.to_thread(parse_document, file.filename, raw_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not content.strip():
            raise HTTPException(status_code=400, detail="文档内容为空")

        chunks = await asyncio.to_thread(chunk_text, content)
        doc = repo_save_doc(conn, self._user_id, file.filename, content, chunks)
        await asyncio.to_thread(get_retriever().index, doc["id"], self._user_id, chunks)
        return doc

    async def query_document(
        self, conn: Connection, doc_id: str, question: str, top_k: int = 5
    ) -> dict:
        """文档问答（RAG）：向量检索 + LLM 生成，避免重复检索"""
        chunks = repo_get_chunks(conn, self._user_id, doc_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="文档不存在")

        # 直接检索 top_k 个相关片段
        results = get_retriever().search(
            question, top_k=top_k, doc_id=doc_id, user_id=self._user_id
        )

        # 拼接上下文
        if results:
            context = "\n\n".join(
                f"[片段 {index} | 来源 {doc.metadata.get('source', doc_id)}]"
                f"\n{doc.page_content}"
                for index, doc in enumerate(results, 1)
            )
        else:
            context = "\n\n".join(
                f"[片段 {index} | 来源 {doc_id}#{index - 1}]\n{chunk}"
                for index, chunk in enumerate(chunks[:top_k], 1)
            )

        # LLM 基于上下文生成答案（不经过 Agent 工具调用，避免重复检索）
        system_prompt = (
            "你是文档问答助手。请基于以下文档内容回答用户的问题。"
            "如果文档内容不足以回答，请如实说明。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"文档内容:\n{context}\n\n问题: {question}"},
        ]

        try:
            answer = await chat_async(messages)
        except LLMError as e:
            answer = f"⚠️ {e}"

        sources = [
            (
                f"[{index}] {doc.metadata.get('source', doc_id)} "
                f"(score={doc.metadata.get('score', 0):.2f}) "
                f"{doc.page_content[:160]}"
                f"{'...' if len(doc.page_content) > 160 else ''}"
            )
            for index, doc in enumerate(results, 1)
        ]

        return {"answer": answer, "sources": sources}
