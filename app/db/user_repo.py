"""用户仓储 —— users 表操作"""

import uuid
from datetime import UTC, datetime
from sqlite3 import Connection


def create_user(conn: Connection, username: str, password_hash: str) -> dict:
    user_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, username, password_hash, now),
    )
    conn.commit()
    return {"id": user_id, "username": username, "created_at": now}


def get_user_by_id(conn: Connection, user_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, username, password_hash, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_username(conn: Connection, username: str) -> dict | None:
    row = conn.execute(
        "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    return dict(row) if row else None


def check_username_exists(conn: Connection, username: str) -> bool:
    row = conn.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    return row is not None
