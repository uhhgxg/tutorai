"""SQLite 数据库 —— 对话和文档的持久化存储"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings


def get_db() -> sqlite3.Connection:
    """获取数据库连接（自动建表）"""
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '新对话',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );
    """)
    conn.commit()


# --- 对话操作 ---

def create_conversation(conn: sqlite3.Connection, title: str = "新对话") -> dict:
    conv_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (conv_id, title, now, now),
    )
    conn.commit()
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}


def list_conversations(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conn: sqlite3.Connection, conv_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    return dict(row) if row else None


def delete_conversation(conn: sqlite3.Connection, conv_id: str) -> bool:
    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    return cur.rowcount > 0


def update_conversation_title(conn: sqlite3.Connection, conv_id: str, title: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, now, conv_id),
    )
    conn.commit()


# --- 消息操作 ---

def add_message(
    conn: sqlite3.Connection, conv_id: str, role: str, content: str
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, now),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id)
    )
    conn.commit()
    return {"id": cur.lastrowid, "conversation_id": conv_id, "role": role, "content": content, "created_at": now}


def get_messages(conn: sqlite3.Connection, conv_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conv_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- 文档操作 ---

def save_document(
    conn: sqlite3.Connection, filename: str, content: str, chunks: list[str]
) -> dict:
    doc_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO documents (id, filename, content, chunk_count, created_at) VALUES (?, ?, ?, ?, ?)",
        (doc_id, filename, content, len(chunks), now),
    )
    for i, chunk in enumerate(chunks):
        conn.execute(
            "INSERT INTO document_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
            (doc_id, i, chunk),
        )
    conn.commit()
    return {"id": doc_id, "filename": filename, "chunk_count": len(chunks), "created_at": now}


def list_documents(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, filename, chunk_count, created_at FROM documents ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_document_chunks(conn: sqlite3.Connection, doc_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
        (doc_id,),
    ).fetchall()
    return [r["content"] for r in rows]


def get_all_chunks(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """返回所有文档块: [(doc_id, chunk_content), ...]"""
    rows = conn.execute("SELECT document_id, content FROM document_chunks").fetchall()
    return [(r["document_id"], r["content"]) for r in rows]


def delete_document(conn: sqlite3.Connection, doc_id: str) -> bool:
    cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    return cur.rowcount > 0
