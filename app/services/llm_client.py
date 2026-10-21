"""LLM 客户端 —— 基于 LangChain ChatOpenAI 的统一调用接口

设计说明：
- 所有 LLM 调用统一走此模块，上层 router 负责异常处理
- 非流式函数（chat, agent_chat）在失败时抛出异常，由 router 层捕获
- 流式函数（chat_stream, agent_chat_stream）在异常时 yield 错误消息
"""

import asyncio
import logging
from collections.abc import Callable, Generator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def _dict_to_messages(messages: list[dict]) -> list[BaseMessage]:
    """将 dict 格式的消息列表转为 LangChain message 对象"""
    role_map = {
        "user": HumanMessage,
        "assistant": AIMessage,
        "system": SystemMessage,
        "tool": ToolMessage,
    }
    result = []
    for m in messages:
        cls = role_map.get(m["role"])
        if cls:
            result.append(cls(content=m["content"]))
        else:
            logger.warning("未知消息角色 '%s'，已跳过", m.get("role"))
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


async def chat_async(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """普通对话（异步），返回完整回复 —— 通过 asyncio.to_thread 避免阻塞事件循环"""
    return await asyncio.to_thread(chat, messages, model=model, temperature=temperature, max_tokens=max_tokens)


def _int_setting(name: str, default: int) -> int:
    """读取整数配置；测试替身或脏环境变量不应破坏 Agent 主流程。"""
    value = getattr(settings, name, default)
    return value if isinstance(value, int) and value > 0 else default


def _notify(event_callback: Callable[[dict], None] | None, event: dict) -> None:
    """通知 Runtime 生命周期事件；观测失败不能影响 Agent 主流程。"""
    if event_callback is None:
        return
    try:
        event_callback(event)
    except Exception:
        logger.debug("Agent event callback failed", exc_info=True)


def _execute_tool(
    tool_call: dict,
    tools: list,
    event_callback: Callable[[dict], None] | None = None,
) -> str:
    """统一执行工具并限制返回长度，避免工具结果挤爆下一轮上下文。"""
    tool_name = str(tool_call.get("name", ""))
    _notify(
        event_callback,
        {"type": "tool_call", "name": tool_name, "tool_call_id": str(tool_call.get("id", ""))},
    )
    matched = next(
        (tool for tool in tools if tool.name == tool_name),
        None,
    )
    if matched is None:
        result = f"未知工具: {tool_name}"
        _notify(event_callback, {"type": "tool_result", "name": tool_name, "ok": False, "chars": len(result)})
        return result

    ok = True
    try:
        result = str(matched.invoke(tool_call.get("args", {})))
    except Exception as exc:
        logger.exception("工具 %s 执行失败", tool_call.get("name"))
        result = f"工具调用失败: {exc}"
        ok = False

    limit = _int_setting("max_tool_result_chars", 3000)
    if len(result) > limit:
        result = result[:limit] + f"\n…（工具结果已截断，最多 {limit} 字符）"
    _notify(event_callback, {"type": "tool_result", "name": tool_name, "ok": ok, "chars": len(result)})
    return result


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
    event_callback: Callable[[dict], None] | None = None,
) -> str:
    """Agent 对话 —— LLM 可自主调用工具（如检索文档），支持多轮工具调用

    Args:
        max_iterations: 最多允许的 LLM 调用轮次（含最终合成答案那次），
                        即工具调用最多 max_iterations-1 轮，然后强制合成最终回复。
    """
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY 未配置")

    max_iterations = max(1, min(max_iterations, _int_setting("max_agent_iterations", 4)))
    llm = get_llm(temperature=temperature, max_tokens=max_tokens, model=model)
    if tools:
        llm = llm.bind_tools(tools)

    langchain_messages = _dict_to_messages(messages)

    for _iteration in range(max_iterations - 1):
        response = llm.invoke(langchain_messages)

        if not response.tool_calls:
            return response.content or ""

        langchain_messages.append(response)
        for tool_call in response.tool_calls:
            result = _execute_tool(tool_call, tools or [], event_callback=event_callback)

            langchain_messages.append(
                ToolMessage(content=result, tool_call_id=tool_call["id"])
            )

    # 达到最大迭代次数后，最后一次 invoke 可能含 tool_calls，需要再请求一次合成最终答案
    final = llm.invoke(langchain_messages)
    return final.content or ""


async def agent_chat_async(
    messages: list[dict],
    tools: list | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    max_iterations: int = 3,
    event_callback: Callable[[dict], None] | None = None,
) -> str:
    """Agent 对话（异步） —— 通过 asyncio.to_thread 避免阻塞事件循环"""
    return await asyncio.to_thread(
        agent_chat, messages, tools=tools, model=model,
        temperature=temperature, max_tokens=max_tokens, max_iterations=max_iterations,
        event_callback=event_callback,
    )


def agent_chat_stream(
    messages: list[dict],
    tools: list | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    max_iterations: int = 3,
    event_callback: Callable[[dict], None] | None = None,
) -> Generator[str, None, None]:
    """Agent 流式对话 —— LLM 自主调用工具，逐 token 返回最终回复

    Args:
        max_iterations: 最多允许的 LLM 调用轮次（含最终流式合成那次），
                        即工具调用最多 max_iterations-1 轮，然后流式合成最终回复。
    """
    if not settings.llm_api_key:
        yield "⚠️ 请先配置 LLM_API_KEY"
        return

    try:
        max_iterations = max(1, min(max_iterations, _int_setting("max_agent_iterations", 4)))
        llm = get_llm(temperature=temperature, max_tokens=max_tokens, model=model)
        if tools:
            llm = llm.bind_tools(tools)

        langchain_messages = _dict_to_messages(messages)

        for _iteration in range(max_iterations - 1):
            # 用 stream 替代 invoke，实现真正的逐 token 输出
            tool_chunks: list[BaseMessage] = []
            is_tool_call = False

            for chunk in llm.stream(langchain_messages):
                if getattr(chunk, "tool_call_chunks", None):
                    is_tool_call = True
                    tool_chunks.append(chunk)
                elif is_tool_call:
                    tool_chunks.append(chunk)
                else:
                    if chunk.content:
                        yield chunk.content

            if not is_tool_call:
                return

            # 从 tool_chunks 重建消息
            reconstructed = tool_chunks[0]
            for c in tool_chunks[1:]:
                reconstructed += c
            langchain_messages.append(reconstructed)

            for tool_call in reconstructed.tool_calls:
                result = _execute_tool(tool_call, tools or [], event_callback=event_callback)

                langchain_messages.append(
                    ToolMessage(content=result, tool_call_id=tool_call["id"])
                )

            yield "\n\n_[Agent 检索完成，正在生成回复...]_\n\n"

        # 达到最大迭代次数后，以流式合成最终答案（省去一次 invoke，调用次数 = max_iterations）
        for chunk in llm.stream(langchain_messages):
            if chunk.content:
                yield chunk.content
    except Exception as e:
        yield f"\n❌ LLM 调用失败: {e}"


TUTOR_SYSTEM_PROMPT = """你是一位专业、耐心的 AI 学习导师，叫 TutorAI。

你拥有以下工具，可根据对话意图自主决定是否调用：
1. retrieve_document — 搜索已上传文档中的相关内容（当用户提问需要参考文档知识时调用）
2. generate_quiz — 根据内容生成练习题（当用户想做题、测试知识掌握程度时调用）
3. list_documents — 列出用户已上传的文档（当用户想查看文档列表时调用）
4. save_memory — 仅当学生明确说“记住/保存”时，保存长期学习目标、偏好或进度
5. list_memory — 查看已保存的学习记忆

教学原则:
- 用通俗易懂的语言解释复杂概念
- 多用生活中的例子和类比
- 鼓励学生思考，而不是直接给答案
- 回答结构清晰，适当使用标题和列表
- 对于编程问题，给出带注释的代码示例
- 发现学生理解有误时，温和地纠正
- 当用户要求出题时，优先调用 generate_quiz 工具

请用中文回答。如果学生用英文提问，就用英文回答。"""


def build_chat_messages(
    history: list[dict],
    user_message: str,
    doc_context: str = "",
    memory_context: str = "",
) -> list[dict]:
    """构建发给 LLM 的完整消息列表"""
    system = TUTOR_SYSTEM_PROMPT
    if doc_context:
        system += f"\n\n以下是学生上传的文档内容，请基于这些内容回答后续问题:\n{doc_context[:settings.max_context_chars]}"
    if memory_context:
        system += (
            "\n\n以下是学生主动保存的学习记忆，仅用于个性化回答；"
            "如果与当前问题冲突，以当前问题为准:\n"
            f"{memory_context[:settings.max_context_chars]}"
        )

    messages: list[dict] = [{"role": "system", "content": system}]
    total_chars = 0
    selected_history: list[dict] = []
    for msg in reversed(history):
        content = str(msg.get("content", ""))
        max_history_chars = _int_setting("max_history_chars", 12000)
        if selected_history and total_chars + len(content) > max_history_chars:
            break
        selected_history.append(msg)
        total_chars += len(content)
    for msg in reversed(selected_history):
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
