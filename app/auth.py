"""用户认证 —— 密码哈希、JWT 签发/验证、获取当前用户依赖注入"""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlite3 import Connection

from app.config import settings
from app.database import get_db

# ── 常量 ──
ALGORITHM = "HS256"
# JWT 密钥：优先用环境变量，否则随机生成（重启后所有 token 失效）
_SECRET_KEY = os.getenv("JWT_SECRET_KEY", hashlib.sha256(os.urandom(64)).hexdigest())

bearer_scheme = HTTPBearer(auto_error=False)


# ── 密码哈希（简单加盐 SHA256，够用即可） ──

def hash_password(password: str) -> str:
    """返回 salt$hash 格式的密码字符串"""
    salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, hashed: str) -> bool:
    """验证密码与哈希是否匹配"""
    try:
        salt, h = hashed.split("$")
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except (ValueError, AttributeError):
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
    """从请求头 Authorization: Bearer <token> 解析当前登录用户

    用法：在需要登录的路由中加一个参数：user: dict = Depends(get_current_user)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
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
    return dict(row)


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
    # 不查库，只返回 id（调用方需要自己查）
    return {"id": user_id}
