"""工具定义 —— LLM Agent 可调用的工具（工厂模式）

不再使用 ContextVar 传递 user_id，而是通过工厂函数在创建时闭包捕获。
每个请求创建自己的工具实例，彻底消除数据泄露风险。

user_id_var 保留供 auth.py 等模块作为请求级别的上下文使用，
但 tools 本身不再依赖它。
"""

import contextvars

from langchain_core.tools import tool

# 请求级别的用户 ID 上下文（仅作为非关键上下文使用，tools 不再依赖它）
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)


def create_user_tools(user_id: str) -> list:
    """为指定用户创建 Agent 工具列表（工厂模式）"""
    return [
        _make_retrieve_document(user_id),
        _make_generate_quiz(user_id),
        _make_list_documents(user_id),
        _make_save_memory(user_id),
        _make_list_memory(user_id),
    ]


def _make_retrieve_document(user_id: str):
    @tool
    def retrieve_document(query: str, doc_id: str | None = None) -> str:
        """搜索已上传文档中的相关内容。当你需要回答一个需要参考文档知识的问题时，调用此工具。
        Args:
            query: 搜索关键词或问题描述
            doc_id: 可选，限定搜索的文档 ID
        """
        from app.services.retriever import search_chunks

        results = search_chunks(query, top_k=5, doc_id=doc_id, user_id=user_id)
        if not results:
            return "未找到相关文档内容。"
        parts = []
        for i, doc in enumerate(results, 1):
            score = doc.metadata.get("score", 0)
            parts.append(f"[片段 {i}]（相关度: {score:.2f}）\n{doc.page_content}")
        return "\n\n".join(parts)

    return retrieve_document


def _make_generate_quiz(user_id: str):
    @tool
    def generate_quiz(
        topic: str = "",
        content: str = "",
        doc_id: str | None = None,
        question_count: int = 3,
        question_type: str = "choice",
    ) -> str:
        """根据知识点生成练习题，会自动从已上传文档中检索相关内容。当用户要求出题、做练习、测试知识掌握程度时，调用此工具。

        Args:
            topic: 出题的知识点描述（如"第三章 决策树"），工具会自动从知识库检索相关内容
            content: 出题依据的文本内容（可选，如果提供了 topic 则优先用 topic 检索）
            doc_id: 可选，限定从哪个文档出题
            question_count: 生成题目数量，默认 3
            question_type: 题型，可选 choice（选择题）/ true_false（判断题）/ fill_blank（填空题）/ short_answer（简答题）/ mixed（混合题型），默认 choice
        """
        from app.services.llm_client import build_quiz_messages, chat
        from app.services.retriever import search_chunks

        if topic:
            results = search_chunks(topic, top_k=5, doc_id=doc_id, user_id=user_id)
            if not results:
                return f"未找到与「{topic}」相关的文档内容。请先上传相关教材，或直接提供内容出题。"
            content = "\n\n".join([doc.page_content for doc in results])

        if not content:
            return "请提供出题的知识点（topic）或内容（content）。"

        messages = build_quiz_messages(content, question_count, question_type)
        result = chat(messages, temperature=0.8, max_tokens=3000)
        return result or "未能生成题目，请稍后重试。"

    return generate_quiz


def _make_list_documents(user_id: str):
    @tool
    def list_documents() -> str:
        """列出当前用户已上传的所有文档。当用户想查看自己的文档列表、选择某个文档进行问答时，调用此工具。"""
        from app.db.engine import get_db_connection

        conn = get_db_connection()
        try:
            rows = conn.execute(
                "SELECT id, filename, chunk_count, created_at FROM documents WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            if not rows:
                return "您还没有上传任何文档。请先上传文档，再进行问答或出题。"
            lines = []
            for i, row in enumerate(rows, 1):
                d = dict(row)
                lines.append(
                    f"{i}. {d['filename']}（{d['chunk_count']} 个片段，上传时间: {d['created_at'][:10]}）ID: {d['id']}"
                )
            return "您已上传以下文档:\n" + "\n".join(lines)
        finally:
            conn.close()

    return list_documents


def _make_save_memory(user_id: str):
    @tool
    def save_memory(content: str, category: str = "general") -> str:
        """保存学生明确要求记住的长期信息，例如学习目标、偏好或当前进度。"""
        from app.db.engine import get_db_connection
        from app.db.memory_repo import save_memory as repo_save_memory

        conn = get_db_connection()
        try:
            memory = repo_save_memory(conn, user_id, content, category, source="chat")
            return f"已记住：[{memory['category']}] {memory['content']}"
        except ValueError as exc:
            return f"无法保存记忆：{exc}"
        finally:
            conn.close()

    return save_memory


def _make_list_memory(user_id: str):
    @tool
    def list_memory() -> str:
        """查看当前学生已经保存的学习目标、偏好和进度记忆。"""
        from app.config import settings
        from app.db.engine import get_db_connection
        from app.db.memory_repo import list_memories as repo_list_memories

        conn = get_db_connection()
        try:
            memories = repo_list_memories(conn, user_id, limit=settings.max_memory_items)
        finally:
            conn.close()

        if not memories:
            return "当前还没有保存的学习记忆。"
        return "\n".join(
            f"- [{memory['category']}] {memory['content']}"
            for memory in memories
        )

    return list_memory
