"""工具定义 —— LLM Agent 可调用的工具"""

import contextvars

from langchain_core.tools import tool

from app.services.retriever import search_chunks

# 用来在线程/协程中传递当前用户 ID
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)


@tool
def retrieve_document(query: str, doc_id: str | None = None) -> str:
    """搜索已上传文档中的相关内容。当你需要回答一个需要参考文档知识的问题时，调用此工具。"""
    uid = user_id_var.get()
    results = search_chunks(query, top_k=5, doc_id=doc_id, user_id=uid)
    if not results:
        return "未找到相关文档内容。"
    parts = []
    for i, doc in enumerate(results, 1):
        score = doc.metadata.get("score", 0)
        parts.append(f"[片段 {i}]（相关度: {score:.2f}）\n{doc.page_content}")
    return "\n\n".join(parts)


AGENT_TOOLS = [retrieve_document]
