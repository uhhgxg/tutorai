"""记忆仓储 —— 用户可检查、可删除的学习记忆。"""

import uuid
from datetime import UTC, datetime
from sqlite3 import Connection

MEMORY_CATEGORIES = {"profile", "goal", "preference", "progress", "general"}
MAX_MEMORY_LENGTH = 500
MAX_MEMORIES_PER_USER = 50


def list_memories(conn: Connection, user_id: str, limit: int = 10) -> list[dict]:
    """按更新时间倒序返回用户记忆，始终带 user_id 隔离条件。"""
    safe_limit = max(1, min(limit, MAX_MEMORIES_PER_USER))
    rows = conn.execute(
        """SELECT id, category, content, source, created_at, updated_at
           FROM memories
          WHERE user_id = ?
          ORDER BY updated_at DESC
          LIMIT ?""",
        (user_id, safe_limit),
    ).fetchall()
    return [dict(row) for row in rows]


def save_memory(
    conn: Connection,
    user_id: str,
    content: str,
    category: str = "general",
    source: str = "chat",
) -> dict:
    """新增或刷新一条记忆，避免同一用户重复保存完全相同的内容。"""
    normalized = " ".join(content.split()).strip()
    if not normalized:
        raise ValueError("记忆内容不能为空")
    if len(normalized) > MAX_MEMORY_LENGTH:
        raise ValueError(f"记忆内容不能超过 {MAX_MEMORY_LENGTH} 个字符")

    category = category if category in MEMORY_CATEGORIES else "general"
    now = datetime.now(UTC).isoformat()
    existing = conn.execute(
        """SELECT id FROM memories
           WHERE user_id = ? AND category = ? AND content = ?""",
        (user_id, category, normalized),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE memories SET source = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (source, now, existing["id"], user_id),
        )
        memory_id = existing["id"]
    else:
        memory_id = uuid.uuid4().hex[:12]
        conn.execute(
            """INSERT INTO memories
               (id, user_id, category, content, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (memory_id, user_id, category, normalized, source, now, now),
        )

    # 轻量上限：保留最近 50 条，避免记忆表无限增长。
    old_rows = conn.execute(
        """SELECT id FROM memories WHERE user_id = ?
           ORDER BY updated_at DESC LIMIT -1 OFFSET ?""",
        (user_id, MAX_MEMORIES_PER_USER),
    ).fetchall()
    if old_rows:
        conn.executemany(
            "DELETE FROM memories WHERE id = ? AND user_id = ?",
            [(row["id"], user_id) for row in old_rows],
        )
    conn.commit()

    row = conn.execute(
        """SELECT id, category, content, source, created_at, updated_at
           FROM memories WHERE id = ? AND user_id = ?""",
        (memory_id, user_id),
    ).fetchone()
    return dict(row)


def delete_memory(conn: Connection, user_id: str, memory_id: str) -> bool:
    """按用户 ID 删除记忆，防止跨用户删除。"""
    cur = conn.execute(
        "DELETE FROM memories WHERE id = ? AND user_id = ?",
        (memory_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0
