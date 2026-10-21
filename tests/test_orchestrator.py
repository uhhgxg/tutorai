"""Agent Runtime 测试：验证统一上下文、工具组合和事件轨迹。"""

import json
import shutil
import tempfile
from pathlib import Path

from app.agent import CapabilityRegistry, ToolRegistry, TurnContext, TutorOrchestrator
from app.agent.trace import TraceRecorder
from app.services import llm_client


class FakeTool:
    def __init__(self, name: str):
        self.name = name


def _context(tools=None) -> TurnContext:
    return TurnContext(
        user_id="runtime-user",
        conversation_id="conversation-1",
        user_message="什么是 RAG？",
        messages=[{"role": "user", "content": "什么是 RAG？"}],
        tools=ToolRegistry(tools or [FakeTool("retrieve_document"), FakeTool("generate_quiz"), FakeTool("save_memory")]),
    )


def _orchestrator(tmp_path: Path):
    return TutorOrchestrator(
        trace_factory=lambda user_id: TraceRecorder(user_id, root=tmp_path),
    )


def _trace_root() -> Path:
    return Path(tempfile.mkdtemp(prefix=".tutorai_test_runtime_", dir=Path.cwd()))


def test_tool_registry_composes_tools_by_capability():
    registry = ToolRegistry([FakeTool("retrieve_document"), FakeTool("generate_quiz"), FakeTool("save_memory")])

    assert registry.names == ("retrieve_document", "generate_quiz", "save_memory")
    assert [tool.name for tool in registry.for_capability("quiz")] == [
        "retrieve_document",
        "generate_quiz",
    ]
    assert [tool.name for tool in registry.for_capability("chat")] == list(registry.names)


def test_capability_registry_rejects_unknown_capability():
    registry = CapabilityRegistry()

    assert registry.names == ("chat", "quiz")
    assert registry.supports("chat")
    assert not registry.supports("study_plan")


def test_stream_events_record_turn_lifecycle(monkeypatch):
    tmp_path = _trace_root()
    def fake_stream(messages, tools, max_iterations, event_callback):
        assert messages[-1]["content"] == "什么是 RAG？"
        assert [tool.name for tool in tools] == ["retrieve_document", "generate_quiz", "save_memory"]
        event_callback({"type": "tool_call", "name": "retrieve_document", "tool_call_id": "tc-1"})
        event_callback({"type": "tool_result", "name": "retrieve_document", "ok": True, "chars": 12})
        yield "RAG 是"
        yield "检索增强生成。"

    try:
        monkeypatch.setattr(llm_client, "agent_chat_stream", fake_stream)
        context = _context()
        events = list(_orchestrator(tmp_path).stream_events(context))

        assert [event.type for event in events] == [
            "started",
            "tool_call",
            "tool_result",
            "delta",
            "delta",
            "completed",
        ]
        assert "".join(event.data for event in events if event.type == "delta") == "RAG 是检索增强生成。"

        trace_files = list((tmp_path / "traces" / "runtime-user" / "chat").glob("*.jsonl"))
        records = [json.loads(line) for line in trace_files[0].read_text(encoding="utf-8").splitlines()]
        assert [record["event"] for record in records] == [
            "started",
            "tool_call",
            "tool_result",
            "completed",
        ]
        assert all("RAG" not in line for line in trace_files[0].read_text(encoding="utf-8").splitlines())
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_sync_run_returns_result_and_records_completion(monkeypatch):
    tmp_path = _trace_root()
    def fake_agent(messages, tools, max_iterations, event_callback):
        event_callback({"type": "tool_call", "name": "list_memory", "tool_call_id": "tc-2"})
        return "已读取学习记忆。"

    try:
        monkeypatch.setattr(llm_client, "agent_chat", fake_agent)
        result = _orchestrator(tmp_path).run(_context())

        assert result.reply == "已读取学习记忆。"
        assert result.turn_id
        trace_file = next((tmp_path / "traces" / "runtime-user" / "chat").glob("*.jsonl"))
        assert '"event": "completed"' in trace_file.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
