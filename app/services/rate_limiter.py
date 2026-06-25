"""请求频率限制 —— 基于 SQLite 持久化，多 worker 共享状态

使用 SQLite 替代内存存储，确保多进程部署下限流一致生效。
自动清理过期记录，表在首次使用时创建。
"""

import os
import sqlite3
import time
from pathlib import Path

from fastapi import HTTPException, Request

from app.config import settings


def _get_db() -> sqlite3.Connection:
    """获取限流器专用的 SQLite 连接"""
    db_dir = Path(settings.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "rate_limiter.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_records (
            client_ip TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rate_ip_ts
        ON rate_records(client_ip, timestamp)
    """)
    return conn


class RateLimiter:
    """滑动窗口频率限制器（SQLite 持久化）

    用法:
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        @router.post("/login")
        async def login(req: Request, ...):
            limiter.check(req)
    """

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def check(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds

        conn = _get_db()
        try:
            # 删除窗口外的记录
            conn.execute(
                "DELETE FROM rate_records WHERE client_ip = ? AND timestamp < ?",
                (client_ip, window_start),
            )
            # 统计当前窗口内的请求数
            count = conn.execute(
                "SELECT COUNT(*) FROM rate_records WHERE client_ip = ? AND timestamp >= ?",
                (client_ip, window_start),
            ).fetchone()[0]

            if count >= self.max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"操作过于频繁，请 {self.window_seconds} 秒后再试",
                )

            conn.execute(
                "INSERT INTO rate_records (client_ip, timestamp) VALUES (?, ?)",
                (client_ip, now),
            )
            conn.commit()
        finally:
            conn.close()

    def clear(self, client_ip: str | None = None) -> None:
        conn = _get_db()
        try:
            if client_ip:
                conn.execute(
                    "DELETE FROM rate_records WHERE client_ip = ?", (client_ip,)
                )
            else:
                conn.execute("DELETE FROM rate_records")
            conn.commit()
        finally:
            conn.close()


# 预置限流器
login_limiter = RateLimiter(max_requests=10, window_seconds=60)
register_limiter = RateLimiter(max_requests=3, window_seconds=300)
