"""文档仓储 —— documents + document_chunks 表操作"""

import uuid
from datetime import UTC, datetime
from sqlite3 import Connection


def save_document(conn: Connection, user_id: str, filename: str, content: str, chunks: list[str]) -> dict:
    doc_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO documents (id, user_id, filename, content, chunk_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (doc_id, user_id, filename, content, len(chunks), now),
    )
    for i, chunk in enumerate(chunks):
        conn.execute(
            "INSERT INTO document_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
            (doc_id, i, chunk),
        )
    conn.commit()
    return {"id": doc_id, "filename": filename, "chunk_count": len(chunks), "created_at": now}


def list_documents(conn: Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, filename, chunk_count, created_at FROM documents WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_document_chunks(conn: Connection, user_id: str, doc_id: str) -> list[str]:
    rows = conn.execute(
        """SELECT dc.content FROM document_chunks dc
         JOIN documents d ON d.id = dc.document_id
        WHERE dc.document_id = ? AND d.user_id = ?
        ORDER BY dc.chunk_index ASC""",
        (doc_id, user_id),
    ).fetchall()
    return [r["content"] for r in rows]


def get_all_chunks(conn: Connection) -> list[tuple[str, str, str]]:
    """返回所有文档块: [(doc_id, user_id, content), ...]"""
    rows = conn.execute(
        """SELECT dc.document_id, d.user_id, dc.content
           FROM document_chunks dc
           JOIN documents d ON d.id = dc.document_id"""
    ).fetchall()
    return [(r["document_id"], r["user_id"], r["content"]) for r in rows]


def delete_document(conn: Connection, user_id: str, doc_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0


def get_document_by_id(conn: Connection, user_id: str, doc_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, filename, chunk_count, created_at FROM documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id),
    ).fetchone()
    return dict(row) if row else None
