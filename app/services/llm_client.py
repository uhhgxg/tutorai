"""LLM 客户端 —— 基于 LangChain ChatOpenAI 的统一调用接口"""

from collections.abc import Generator

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.config import settings


def _dict_to_messages(messages: list[dict]) -> list[BaseMessage]:
    """将 dict 格式的消息列表转为 LangChain message 对象"""
    role_map = {
        "user": HumanMessage,
        "assistant": AIMessage,
        "system": SystemMessage,
    }
    result = []
    for m in messages:
        cls = role_map.get(m["role"])
        if cls:
            result.append(cls(content=m["content"]))
    return result


def get_llm(
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str | None = None,
) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=model or settings.llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """普通对话（非流式），返回完整回复"""
    if not settings.llm_api_key:
        return "⚠️ 请先配置 LLM_API_KEY（复制 .env.example 为 .env 并填入你的 API Key）"

    try:
        llm = get_llm(temperature=temperature, max_tokens=max_tokens, model=model)
        resp = llm.invoke(_dict_to_messages(messages))
        return resp.content or ""
    except Exception as e:
        return f"❌ LLM 调用失败: {e}"


def chat_stream(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> Generator[str, None, None]:
    """流式对话 —— 逐 token 返回，适合实时显示"""
    if not settings.llm_api_key:
        yield "⚠️ 请先配置 LLM_API_KEY"
        return

    try:
        llm = get_llm(temperature=temperature, max_tokens=max_tokens, model=model)
        for chunk in llm.stream(_dict_to_messages(messages)):
            if chunk.content:
                yield chunk.content
    except Exception as e:
        yield f"\n❌ 调用失败: {e}"


TUTOR_SYSTEM_PROMPT = """你是一位专业、耐心的 AI 学习导师，叫 TutorAI。

教学原则:
- 用通俗易懂的语言解释复杂概念
- 多用生活中的例子和类比
- 鼓励学生思考，而不是直接给答案
- 回答结构清晰，适当使用标题和列表
- 对于编程问题，给出带注释的代码示例
- 发现学生理解有误时，温和地纠正

请用中文回答。如果学生用英文提问，就用英文回答。"""


def build_chat_messages(
    history: list[dict],
    user_message: str,
    doc_context: str = "",
) -> list[dict]:
    """构建发给 LLM 的完整消息列表"""
    system = TUTOR_SYSTEM_PROMPT
    if doc_context:
        system += f"\n\n以下是学生上传的文档内容，请基于这些内容回答后续问题:\n{doc_context[:3000]}"

    messages: list[dict] = [{"role": "system", "content": system}]
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


QUIZ_SYSTEM_PROMPT = """你是一位经验丰富的教育测评专家。根据提供的知识点，生成高质量的练习题。

要求:
- 题目考察理解能力，不是死记硬背
- 每道题 4 个选项 (A/B/C/D)，干扰项要有迷惑性
- 最后附上正确答案和解析
- 用 Markdown 格式输出"""


def build_quiz_messages(content: str, question_count: int) -> list[dict]:
    return [
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"请根据以下内容生成 {question_count} 道选择题:\n\n{content}",
        },
    ]
