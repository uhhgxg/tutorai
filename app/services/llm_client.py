"""LLM 客户端 —— 基于 LangChain ChatOpenAI 的统一调用接口

设计说明：
- 所有 LLM 调用统一走此模块，上层 router 负责异常处理
- 非流式函数（chat, agent_chat）在失败时抛出异常，由 router 层捕获
- 流式函数（chat_stream, agent_chat_stream）在异常时 yield 错误消息
"""

from collections.abc import Generator

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage

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


class LLMError(Exception):
    """LLM 调用失败时抛出的异常"""
    pass


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
        raise LLMError("LLM_API_KEY 未配置")

    llm = get_llm(temperature=temperature, max_tokens=max_tokens, model=model)
    resp = llm.invoke(_dict_to_messages(messages))
    return resp.content or ""


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


def agent_chat(
    messages: list[dict],
    tools: list | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    max_iterations: int = 3,
) -> str:
    """Agent 对话 —— LLM 可自主调用工具（如检索文档），支持多轮工具调用"""
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY 未配置")

    llm = get_llm(temperature=temperature, max_tokens=max_tokens, model=model)
    if tools:
        llm = llm.bind_tools(tools)

    langchain_messages = _dict_to_messages(messages)

    for iteration in range(max_iterations):
        response = llm.invoke(langchain_messages)

        if not response.tool_calls:
            return response.content or ""

        langchain_messages.append(response)
        for tool_call in response.tool_calls:
            matched = next(
                (t for t in tools if t.name == tool_call["name"]),
                None,
            )
            if matched:
                try:
                    result = matched.invoke(tool_call["args"])
                except Exception as e:
                    result = f"工具调用失败: {e}"
            else:
                result = f"未知工具: {tool_call['name']}"

            langchain_messages.append(
                ToolMessage(content=result, tool_call_id=tool_call["id"])
            )

    return langchain_messages[-1].content or ""


def agent_chat_stream(
    messages: list[dict],
    tools: list | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    max_iterations: int = 3,
) -> Generator[str, None, None]:
    """Agent 流式对话 —— LLM 自主调用工具，逐 token 返回最终回复"""
    if not settings.llm_api_key:
        yield "⚠️ 请先配置 LLM_API_KEY"
        return

    try:
        llm = get_llm(temperature=temperature, max_tokens=max_tokens, model=model)
        if tools:
            llm = llm.bind_tools(tools)

        langchain_messages = _dict_to_messages(messages)

        for iteration in range(max_iterations):
            response = llm.invoke(langchain_messages)

            if not response.tool_calls:
                # 无需工具调用，直接返回 invoke 结果（不重复请求）
                yield response.content or ""
                return

            # 执行工具调用
            langchain_messages.append(response)
            for tool_call in response.tool_calls:
                matched = next(
                    (t for t in tools if t.name == tool_call["name"]),
                    None,
                )
                if matched:
                    try:
                        result = matched.invoke(tool_call["args"])
                    except Exception as e:
                        result = f"工具调用失败: {e}"
                else:
                    result = f"未知工具: {tool_call['name']}"

                langchain_messages.append(
                    ToolMessage(content=result, tool_call_id=tool_call["id"])
                )

            yield "\n\n_[Agent 检索完成，正在生成回复...]_\n\n"

        # 达到最大迭代次数后，再请求一次并以流式返回最终结果
        for chunk in llm.stream(langchain_messages):
            if chunk.content:
                yield chunk.content
    except Exception as e:
        yield f"\n❌ LLM 调用失败: {e}"


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


QUESTION_TYPE_PROMPTS = {
    "choice": "生成选择题，每道题 4 个选项 (A/B/C/D)，干扰项要有迷惑性，最后附上正确答案和解析。",
    "true_false": "生成判断题，每道题给出一个陈述，要求学生判断对错，并附上正确答案和解析。",
    "fill_blank": "生成填空题，每道题在关键知识点处留空（用 ____ 表示），附上正确答案和解析。",
    "short_answer": "生成简答题，每道题考察对知识点的理解和概括能力，附上参考答案要点和解析。",
    "mixed": "混合生成多种题型（包括选择题、判断题、填空题、简答题），每道题附上正确答案和解析。",
}


def build_quiz_messages(content: str, question_count: int, question_type: str = "choice") -> list[dict]:
    type_prompt = QUESTION_TYPE_PROMPTS.get(question_type, QUESTION_TYPE_PROMPTS["choice"])
    system = f"""你是一位经验丰富的教育测评专家。根据提供的知识点，生成高质量的练习题。

要求:
- 题目考察理解能力，不是死记硬背
- {type_prompt}
- 用 Markdown 格式输出，题目用数字编号"""
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"请根据以下内容生成 {question_count} 道{ {'choice':'选择题','true_false':'判断题','fill_blank':'填空题','short_answer':'简答题','mixed':'混合题型' }.get(question_type, '练习题') }:\n\n{content}",
        },
    ]
