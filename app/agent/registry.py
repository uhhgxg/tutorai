"""运行时注册表与每轮工具组合策略。"""

from __future__ import annotations

from collections.abc import Iterable


class CapabilityRegistry:
    """运行时支持的能力清单，防止未知 capability 静默落到 chat。"""

    def __init__(self, capabilities: Iterable[str] | None = None):
        values = {"chat", "quiz"} if capabilities is None else capabilities
        self._capabilities = frozenset(values)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._capabilities))

    def supports(self, capability: str) -> bool:
        return capability in self._capabilities


class ToolRegistry:
    """把工具实例集中管理，并按 capability 选择本轮工具。

    chat 默认使用完整工具面；quiz 只挂载和出题直接相关的工具。
    规则集中在这里，后续新增能力时不需要修改 ChatService。
    """

    _CAPABILITY_TOOLS = {
        "quiz": frozenset({"retrieve_document", "generate_quiz"}),
    }

    def __init__(self, tools: Iterable[object]):
        self._tools = tuple(tools)
        self._by_name = {
            getattr(tool, "name", ""): tool
            for tool in self._tools
            if getattr(tool, "name", "")
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name)

    def for_capability(self, capability: str = "chat") -> list[object]:
        allowed = self._CAPABILITY_TOOLS.get(capability)
        if allowed is None:
            return list(self._tools)
        return [tool for tool in self._tools if getattr(tool, "name", "") in allowed]
