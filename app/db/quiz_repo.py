"""出题结果仓储 —— quiz_results 表操作"""

import re
import uuid
from datetime import UTC, datetime
from sqlite3 import Connection


def save_quiz_result(conn: Connection, user_id: str, title: str, result_text: str, question_count: int | None = None) -> dict:
    result_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()
    if question_count is not None and question_count > 0:
        q_count = question_count
    else:
        # 前端未传题数时，从文本中自动计数
        # 匹配多种题号格式：1.  1、  1)  1）  **1.**  ### 1. 等
        q_count = len(re.findall(r"(?:^|\n)\s*(?:[*#\s]*)\d+[.、）)]", result_text))
        # 兜底：如果上面没匹配到，尝试更宽松的模式
        if q_count == 0:
            q_count = len(re.findall(r"\d+[.、）)]\s*\S", result_text))
    conn.execute(
        "INSERT INTO quiz_results (id, user_id, title, result_text, question_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (result_id, user_id, title, result_text, q_count, now),
    )
    conn.commit()
    return {"id": result_id, "title": title, "question_count": q_count, "created_at": now}


def list_quiz_results(conn: Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, question_count, created_at FROM quiz_results WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_quiz_result(conn: Connection, user_id: str, result_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM quiz_results WHERE id = ? AND user_id = ?", (result_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def delete_quiz_result(conn: Connection, user_id: str, result_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM quiz_results WHERE id = ? AND user_id = ?", (result_id, user_id)
    )
    conn.commit()
    return cur.rowcount > 0
