"""用户认证 —— 密码哈希、JWT 签发/验证、令牌黑名单、获取当前用户"""

import logging
import re
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db.engine import get_db
from app.db.user_repo import get_user_by_id
from app.services.tools import user_id_var

logger = logging.getLogger(__name__)

# ── 常量 ──
ALGORITHM = "HS256"
_SECRET_KEY: str | None = None
BLACKLIST_CLEANUP_INTERVAL = 3600  # 每小时清理一次过期黑名单
_last_cleanup: float = 0

# ── 令牌黑名单（独立 SQLite 文件，避免阻塞主库） ──

_BLACKLIST_DB_PATH: Path | None = None


def _init_blacklist_path() -> Path:
    global _BLACKLIST_DB_PATH
    if _BLACKLIST_DB_PATH is not None:
        return _BLACKLIST_DB_PATH
    db_dir = Path(settings.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    _BLACKLIST_DB_PATH = db_dir / "blacklist.db"
    return _BLACKLIST_DB_PATH


@contextmanager
def _blacklist_conn() -> Generator[sqlite3.Connection, None, None]:
    path = _init_blacklist_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS token_blacklist (
                token TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        # 迁移: 旧表没有 expires_at 列，后续清理需要
        with suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE token_blacklist ADD COLUMN expires_at TEXT")
        yield conn
    finally:
        conn.close()


def _cleanup_expired_blacklist() -> None:
    """清理已过期的黑名单记录（JWT 有效期 7 天后的记录可以安全删除）"""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < BLACKLIST_CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    try:
        with _blacklist_conn() as conn:
            cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
            deleted = conn.execute(
                "DELETE FROM token_blacklist WHERE expires_at < ?", (cutoff,)
            ).rowcount
            conn.commit()
            if deleted:
                logger.info("已清理 %d 条过期黑名单记录", deleted)
    except Exception as e:
        logger.warning("清理黑名单失败: %s", e)


def blacklist_token(token: str) -> None:
    expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    now = datetime.now(UTC).isoformat()
    with _blacklist_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO token_blacklist (token, created_at, expires_at) VALUES (?, ?, ?)",
            (token, now, expires_at),
        )
        conn.commit()
    _cleanup_expired_blacklist()


def is_token_blacklisted(token: str) -> bool:
    _cleanup_expired_blacklist()
    with _blacklist_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM token_blacklist WHERE token = ?", (token,)
        ).fetchone()
        return row is not None


def _get_secret_key() -> str:
    global _SECRET_KEY
    if _SECRET_KEY is not None:
        return _SECRET_KEY
    _SECRET_KEY = settings.jwt_secret_key
    return _SECRET_KEY


bearer_scheme = HTTPBearer(auto_error=False)


def validate_password_strength(password: str) -> str | None:
    """校验密码强度，不合法则返回错误信息"""
    if len(password) < 8:
        return "密码长度至少 8 位"
    if not re.search(r"[A-Za-z]", password):
        return "密码需包含至少一个字母"
    if not re.search(r"[0-9]", password):
        return "密码需包含至少一个数字"
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: str) -> str:
    """签发 JWT token（7 天有效）"""
    payload = {
        "sub": user_id,
        "exp": datetime.now(UTC) + timedelta(days=7),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    """解码 JWT token，返回 user_id；无效则返回 None"""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """从请求头 Authorization: Bearer <token> 解析当前登录用户"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if is_token_blacklisted(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )
    user = get_user_by_id(conn, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    user_id_var.set(user["id"])
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    """和 get_current_user 类似，但不强制登录"""
    if credentials is None:
        return None
    if is_token_blacklisted(credentials.credentials):
        return None
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        return None
    user_id_var.set(user_id)
    return {"id": user_id}
