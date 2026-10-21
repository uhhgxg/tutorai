"""对话仓储 —— conversations + messages 表操作"""

import uuid
from datetime import UTC, datetime
from sqlite3 import Connection


def create_conversation(conn: Connection, user_id: str, title: str = "新对话") -> dict:
    conv_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (conv_id, user_id, title, now, now),
    )
    conn.commit()
    return {"id": conv_id, "user_id": user_id, "title": title, "created_at": now, "updated_at": now}


def list_conversations(conn: Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conn: Connection, conv_id: str, user_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def delete_conversation(conn: Connection, conv_id: str, user_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0


def update_conversation_title(conn: Connection, conv_id: str, user_id: str, title: str) -> None:
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (title, now, conv_id, user_id),
    )
    conn.commit()


def add_message(conn: Connection, conv_id: str, user_id: str, role: str, content: str) -> dict | None:
    """向对话添加消息。若对话不属于该用户则返回 None。"""
    owner = conn.execute(
        "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id)
    ).fetchone()
    if not owner:
        return None

    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, now),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id)
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "created_at": now,
    }


def get_messages(conn: Connection, conv_id: str, user_id: str, limit: int | None = None) -> list[dict]:
    """获取对话消息。通过子查询确保只能查询属于该用户的对话。"""
    if limit:
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE conversation_id = ?
                 AND conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)
               ORDER BY created_at DESC LIMIT ?""",
            (conv_id, user_id, limit),
        ).fetchall()
        rows = list(reversed(rows))
    else:
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE conversation_id = ?
                 AND conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)
               ORDER BY created_at ASC""",
            (conv_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]
