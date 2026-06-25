"""认证 API —— 注册、登录、退出、获取当前用户信息"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlite3 import Connection

from app.database import get_db
from app.auth import (
    hash_password,
    verify_password,
    create_token,
    validate_password_strength,
    get_current_user,
    blacklist_token,
)
from app.services.rate_limiter import login_limiter, register_limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── 请求/响应模型 ──

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_一-鿿]+$")
    password: str = Field(..., min_length=8, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    token: str
    user_id: str
    username: str


class UserResponse(BaseModel):
    id: str
    username: str
    created_at: str


# ── 依赖注入：获取数据库连接 ──

def get_conn():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


# ── 路由 ──

@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, request: Request, conn: Connection = Depends(get_conn)):
    """注册新用户"""
    register_limiter.check(request)

    # 密码强度校验
    err = validate_password_strength(req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # 检查用户名是否已存在
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?", (req.username,)
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    password_hash = hash_password(req.password)

    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, req.username, password_hash, now),
    )
    conn.commit()

    token = create_token(user_id)
    return AuthResponse(token=token, user_id=user_id, username=req.username)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request, conn: Connection = Depends(get_conn)):
    """用户登录"""
    login_limiter.check(request)

    row = conn.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (req.username,),
    ).fetchone()
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(row["id"])
    return AuthResponse(token=token, user_id=row["id"], username=row["username"])


@router.delete("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    user: dict = Depends(get_current_user),
):
    """退出登录（将当前令牌加入黑名单）"""
    if credentials:
        blacklist_token(credentials.credentials)
    return {"ok": True, "detail": "已退出登录"}


@router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserResponse(id=user["id"], username=user["username"], created_at=user["created_at"])
