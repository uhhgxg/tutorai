"""用户认证 —— 密码哈希、JWT 签发/验证、令牌黑名单、获取当前用户"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlite3 import Connection

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.database import get_db
from app.services.tools import user_id_var

# ── 常量 ──
ALGORITHM = "HS256"
_SECRET_KEY = settings.jwt_secret_key

bearer_scheme = HTTPBearer(auto_error=False)

# ── 令牌黑名单（SQLite 持久化，多 worker 共享） ──


def _blacklist_db() -> sqlite3.Connection:
    db_dir = Path(settings.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_dir / "blacklist.db"), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_blacklist (
            token TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
    """)
    return conn


def blacklist_token(token: str) -> None:
    conn = _blacklist_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO token_blacklist (token, created_at) VALUES (?, ?)",
            (token, now),
        )
        conn.commit()
    finally:
        conn.close()


def is_token_blacklisted(token: str) -> bool:
    conn = _blacklist_db()
    try:
        row = conn.execute(
            "SELECT 1 FROM token_blacklist WHERE token = ?", (token,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ── 密码校验 ──

def validate_password_strength(password: str) -> str | None:
    """校验密码强度，不合法则返回错误信息"""
    if len(password) < 8:
        return "密码长度至少 8 位"
    if not re.search(r"[A-Za-z]", password):
        return "密码需包含至少一个字母"
    if not re.search(r"[0-9]", password):
        return "密码需包含至少一个数字"
    return None


# ── 密码哈希（bcrypt） ──

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT ──

def create_token(user_id: str) -> str:
    """签发 JWT token（7 天有效）"""
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    """解码 JWT token，返回 user_id；无效则返回 None"""
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ── FastAPI 依赖注入 ──

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: Connection = Depends(get_db),
) -> dict:
    """从请求头 Authorization: Bearer <token> 解析当前登录用户"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 检查黑名单
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
    # 查数据库确认用户存在
    row = conn.execute(
        "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    user = dict(row)
    # 设置 user_id 到 contextvar，供 tools.retrieve_document 使用
    user_id_var.set(user["id"])
    return user


# ── 可选的用户依赖（不需要登录也能访问） ──

def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    """和 get_current_user 类似，但不强制登录"""
    if credentials is None:
        return None
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        return None
    user_id_var.set(user_id)
    return {"id": user_id}
