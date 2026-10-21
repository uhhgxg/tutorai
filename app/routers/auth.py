"""认证 API —— 注册、登录、退出、获取当前用户信息"""


from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.auth import (
    blacklist_token,
    create_token,
    get_current_user,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.db.engine import get_db
from app.db.user_repo import check_username_exists, get_user_by_username
from app.db.user_repo import create_user as repo_create_user
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


# ── 路由 ──

@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, request: Request, conn: Connection = Depends(get_db)):
    """注册新用户"""
    register_limiter.check(request)

    err = validate_password_strength(req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    if check_username_exists(conn, req.username):
        raise HTTPException(status_code=409, detail="用户名已存在")

    password_hash = hash_password(req.password)
    user = repo_create_user(conn, req.username, password_hash)
    token = create_token(user["id"])
    return AuthResponse(token=token, user_id=user["id"], username=req.username)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request, conn: Connection = Depends(get_db)):
    """用户登录"""
    login_limiter.check(request)

    user = get_user_by_username(conn, req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user["id"])
    return AuthResponse(token=token, user_id=user["id"], username=user["username"])


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
