"""轻量级 L1 执行轨迹。

只记录阶段和元数据，不记录完整 prompt、用户原文或工具结果，避免把敏感
内容无意间写入日志。目录结构沿用 ``trace/<surface>/<date>.jsonl`` 的思路。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Lock

from app.config import settings

logger = logging.getLogger(__name__)
_TRACE_LOCK = Lock()


class TraceRecorder:
    """按用户和日期追加 Agent 执行事件。写入失败不影响主链路。"""

    def __init__(self, user_id: str, root: Path | None = None, surface: str = "chat"):
        safe_user_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", user_id)[:80] or "anonymous"
        self._directory = (root or Path(settings.db_path).parent) / "traces" / safe_user_id / surface

    @property
    def directory(self) -> Path:
        return self._directory

    def record(self, turn_id: str, event_type: str, metadata: dict[str, object] | None = None) -> None:
        payload = {
            "turn_id": turn_id,
            "event": event_type,
            "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "metadata": metadata or {},
        }
        path = self._directory / f"{date.today().isoformat()}.jsonl"
        try:
            with _TRACE_LOCK:
                self._directory.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError:
            logger.debug("Agent trace 写入失败: %s", path, exc_info=True)
