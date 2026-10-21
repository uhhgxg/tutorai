"""TutorAI 的统一 Agent 执行入口。

这里对应 DeepTutor 的 ``TurnEngine -> Orchestrator -> capability`` 边界，
但保持 TutorAI 当前的 LangChain 调用实现不变，只把生命周期和事件收口。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Generator
from typing import Any

from app.agent.contracts import AgentResult, StreamEvent, TurnContext
from app.agent.registry import CapabilityRegistry, ToolRegistry
from app.agent.trace import TraceRecorder
from app.config import settings
from app.services import llm_client


class TutorOrchestrator:
    """路由一次 turn，并提供同步结果和统一流式事件两种适配方式。"""

    def __init__(
        self,
        trace_factory: Callable[[str], TraceRecorder] = TraceRecorder,
        capability_registry: CapabilityRegistry | None = None,
    ):
        self._trace_factory = trace_factory
        self._capabilities = capability_registry or CapabilityRegistry()

    def _validate_capability(self, context: TurnContext) -> None:
        if not self._capabilities.supports(context.capability):
            supported = ", ".join(self._capabilities.names)
            raise ValueError(f"未知能力: {context.capability}；当前支持: {supported}")

    @staticmethod
    def _tools(context: TurnContext) -> list[object]:
        if isinstance(context.tools, ToolRegistry):
            return context.tools.for_capability(context.capability)
        return list(context.tools)  # type: ignore[arg-type]

    @staticmethod
    def _event(context: TurnContext, event_type: str, **metadata: object) -> StreamEvent:
        return StreamEvent(type=event_type, turn_id=context.turn_id, metadata=metadata)

    def _callback(
        self,
        context: TurnContext,
        recorder: TraceRecorder,
        pending: deque[StreamEvent] | None = None,
    ) -> Callable[[dict[str, Any]], None]:
        def on_event(event: dict[str, Any]) -> None:
            event_type = str(event.get("type", "agent_event"))
            metadata = {
                key: value
                for key, value in event.items()
                if key != "type" and isinstance(value, (str, int, float, bool))
            }
            recorder.record(context.turn_id, event_type, metadata)
            if pending is not None:
                pending.append(self._event(context, event_type, **metadata))

        return on_event

    def run(self, context: TurnContext) -> AgentResult:
        """执行非流式 turn。"""
        self._validate_capability(context)
        recorder = self._trace_factory(context.user_id)
        recorder.record(
            context.turn_id,
            "started",
            {"capability": context.capability, "tool_count": len(self._tools(context))},
        )
        try:
            reply = llm_client.agent_chat(
                context.messages,
                tools=self._tools(context),
                max_iterations=settings.max_agent_iterations,
                event_callback=self._callback(context, recorder),
            )
        except Exception as exc:
            recorder.record(context.turn_id, "error", {"error_type": type(exc).__name__})
            raise
        recorder.record(context.turn_id, "completed", {"reply_chars": len(reply)})
        return AgentResult(reply=reply, turn_id=context.turn_id)

    async def run_async(self, context: TurnContext) -> AgentResult:
        """异步适配器；模型调用仍在线程中执行，避免阻塞 FastAPI 事件循环。"""
        self._validate_capability(context)
        recorder = self._trace_factory(context.user_id)
        recorder.record(
            context.turn_id,
            "started",
            {"capability": context.capability, "tool_count": len(self._tools(context))},
        )
        try:
            reply = await llm_client.agent_chat_async(
                context.messages,
                tools=self._tools(context),
                max_iterations=settings.max_agent_iterations,
                event_callback=self._callback(context, recorder),
            )
        except Exception as exc:
            recorder.record(context.turn_id, "error", {"error_type": type(exc).__name__})
            raise
        recorder.record(context.turn_id, "completed", {"reply_chars": len(reply)})
        return AgentResult(reply=reply, turn_id=context.turn_id)

    def stream_events(self, context: TurnContext) -> Generator[StreamEvent, None, None]:
        """输出统一事件；HTTP 文本流由 ChatService 做最后一层适配。"""
        self._validate_capability(context)
        recorder = self._trace_factory(context.user_id)
        recorder.record(
            context.turn_id,
            "started",
            {"capability": context.capability, "tool_count": len(self._tools(context))},
        )
        pending: deque[StreamEvent] = deque()
        yield self._event(context, "started", capability=context.capability)

        reply_chars = 0
        try:
            stream = llm_client.agent_chat_stream(
                context.messages,
                tools=self._tools(context),
                max_iterations=settings.max_agent_iterations,
                event_callback=self._callback(context, recorder, pending),
            )
            for token in stream:
                while pending:
                    yield pending.popleft()
                if token:
                    reply_chars += len(token)
                    yield StreamEvent(type="delta", turn_id=context.turn_id, data=token)
            while pending:
                yield pending.popleft()
            recorder.record(context.turn_id, "completed", {"reply_chars": reply_chars})
            yield self._event(context, "completed", reply_chars=reply_chars)
        except Exception as exc:
            recorder.record(context.turn_id, "error", {"error_type": type(exc).__name__})
            yield self._event(context, "error", error_type=type(exc).__name__)
            raise

    def stream_text(self, context: TurnContext) -> Generator[str, None, None]:
        """兼容现有纯文本 StreamingResponse 的适配器。"""
        for event in self.stream_events(context):
            if event.type == "delta":
                yield event.data
