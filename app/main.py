"""TutorAI — FastAPI 应用入口

一个基于 AI 的智能学习助手，支持:
- 多轮对话辅导
- 文档上传与检索问答 (RAG)
- 自动生成练习题
"""

from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import auth, chat, document, quiz, pages
from app.database import get_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化数据库和检索索引"""
    from app.config import settings

    if not settings.llm_api_key:
        logger.warning("⚠️ LLM_API_KEY 未配置！聊天和出题功能将不可用。请设置环境变量或在 .env 文件中配置。")
    else:
        logger.info("LLM API Key 已配置，模型: %s", settings.llm_model)
    yield


app = FastAPI(
    title="TutorAI",
    description="AI 智能学习助手 — 支持对话辅导、文档问答、出题测试",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — 允许前后端分离部署
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(404)
async def not_found(request, exc):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        content=(Path(__file__).parent / "templates" / "404.html").read_text(encoding="utf-8"),
        status_code=404,
    )


@app.exception_handler(403)
async def forbidden(request, exc):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        content=(Path(__file__).parent / "templates" / "403.html").read_text(encoding="utf-8"),
        status_code=403,
    )


@app.get("/health")
def health_check():
    """容器编排健康检查端点"""
    from app.config import settings
    return {"status": "ok", "api_key_configured": bool(settings.llm_api_key)}

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 注册路由
app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(chat.router)
app.include_router(document.router)
app.include_router(quiz.router)
