"""Agent Runtime 的最小数据契约。

这些对象让 Router、Service、Agent 和未来的 WebSocket 适配器共享同一套
请求/事件格式，避免每个入口各自拼装一套隐式参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(slots=True)
class TurnContext:
    """一次用户 turn 的完整执行上下文。"""

    user_id: str
    conversation_id: str
    user_message: str
    messages: list[dict]
    tools: object
    capability: str = "chat"
    turn_id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """运行时统一事件；文本适配器只消费 ``delta`` 事件。"""

    type: str
    turn_id: str
    data: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds")
    )


@dataclass(frozen=True, slots=True)
class AgentResult:
    """非流式执行结果，为后续增加 token 用量/引用来源预留位置。"""

    reply: str
    turn_id: str
    metadata: dict[str, object] = field(default_factory=dict)
