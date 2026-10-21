"""记忆仓储测试 —— 验证去重、用户隔离和删除边界。"""

import sqlite3

from app.db.memory_repo import delete_memory, list_memories, save_memory


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE memories (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, category TEXT NOT NULL,
            content TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(user_id, category, content)
        )"""
    )
    conn.commit()
    return conn


def test_save_memory_deduplicates_same_user():
    conn = _make_db()
    first = save_memory(conn, "u1", "  学习目标是 Agent 开发  ", "goal")
    second = save_memory(conn, "u1", "学习目标是 Agent 开发", "goal")
    assert first["id"] == second["id"]
    assert len(list_memories(conn, "u1")) == 1


def test_memory_isolated_by_user_and_delete_is_scoped():
    conn = _make_db()
    memory = save_memory(conn, "u1", "只属于用户一", "general")
    assert list_memories(conn, "u2") == []
    assert delete_memory(conn, "u2", memory["id"]) is False
    assert delete_memory(conn, "u1", memory["id"]) is True
