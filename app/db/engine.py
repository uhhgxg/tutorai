"""数据库引擎 —— 连接管理、重试机制、统一依赖注入

修复：SQLite 并发写入冲突（busy_timeout + 指数退避重试）
"""

import random
import sqlite3
import time
from collections.abc import Generator
from pathlib import Path

from app.config import settings

MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.05  # 50ms base


def get_db_path() -> Path:
    p = Path(settings.db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def create_connection() -> sqlite3.Connection:
    """创建原始连接（不含建表/迁移）"""
    path = get_db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def execute_with_retry(
    conn: sqlite3.Connection, sql: str, params: tuple = ()
) -> sqlite3.Cursor:
    """带指数退避重试的 SQL 执行，解决 SQLite 并发写入冲突"""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2**attempt) + random.random() * 0.02
                time.sleep(delay)
                last_exc = e
                continue
            raise
    raise last_exc  # type: ignore[misc]


def commit_with_retry(conn: sqlite3.Connection) -> None:
    """带重试的提交"""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2**attempt) + random.random() * 0.02
                time.sleep(delay)
                last_exc = e
                continue
            raise
    raise last_exc  # type: ignore[misc]


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI 依赖注入：获取数据库连接（已建表），请求结束后自动关闭"""
    conn = _get_initialized_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_db_connection() -> sqlite3.Connection:
    """普通函数：获取直接可用的数据库连接（适用于测试和脚本），调用者需自行关闭"""
    return _get_initialized_connection()


def _get_initialized_connection() -> sqlite3.Connection:
    """获取已初始化（建表+迁移）的连接"""
    conn = create_connection()
    _init_tables(conn)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """数据迁移：添加新版本引入的字段"""
    cur = conn.execute("PRAGMA table_info(conversations)")
    cols = {r[1] for r in cur.fetchall()}
    if "user_id" not in cols:
        conn.executescript("""
            ALTER TABLE conversations ADD COLUMN user_id TEXT NOT NULL DEFAULT '';
            ALTER TABLE documents ADD COLUMN user_id TEXT NOT NULL DEFAULT '';
        """)
        conn.commit()
    # 修复：把 user_id 为空的旧记录关联到第一个用户
    empty_count = conn.execute("SELECT COUNT(*) FROM conversations WHERE user_id = ''").fetchone()[0]
    if empty_count > 0:
        first_user = conn.execute("SELECT id FROM users ORDER BY created_at LIMIT 1").fetchone()
        if first_user:
            conn.execute("UPDATE conversations SET user_id = ? WHERE user_id = ''", (first_user[0],))
            conn.execute("UPDATE documents SET user_id = ? WHERE user_id = ''", (first_user[0],))
            conn.commit()


def _init_tables(conn: sqlite3.Connection) -> None:
    """初始化数据库表结构"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '新对话',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS quiz_results (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            result_text TEXT NOT NULL,
            question_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'chat',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (user_id, category, content),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_memories_user_updated
            ON memories(user_id, updated_at DESC);
    """)
    conn.commit()
