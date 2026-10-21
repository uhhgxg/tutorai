"""TutorAI — FastAPI 应用入口

一个基于 AI 的智能学习助手，支持:
- 多轮对话辅导
- 文档上传与检索问答 (RAG)
- 自动生成练习题
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.logging_config import setup_logging
from app.routers import auth, chat, document, memory, pages, quiz

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化数据库和检索索引"""
    if not settings.llm_api_key:
        logger.warning("⚠️ LLM_API_KEY 未配置！聊天和出题功能将不可用。请设置环境变量或在 .env 文件中配置。")
    else:
        logger.info("LLM API Key 已配置，模型: %s", settings.llm_model)
    # 仅在显式开启时预热，避免启动阶段阻塞在嵌入模型加载/下载。
    if settings.preload_retriever:
        try:
            from app.services.retriever import get_retriever
            get_retriever()
            logger.info("Retriever 预热完成")
        except Exception as e:
            logger.warning("Retriever 预热失败（可能在首次请求时自动初始化）: %s", e)
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
    return HTMLResponse(
        content=(Path(__file__).parent / "templates" / "404.html").read_text(encoding="utf-8"),
        status_code=404,
    )


@app.exception_handler(403)
async def forbidden(request, exc):
    return HTMLResponse(
        content=(Path(__file__).parent / "templates" / "403.html").read_text(encoding="utf-8"),
        status_code=403,
    )


@app.get("/health")
def health_check():
    """容器编排健康检查端点"""
    return {"status": "ok"}

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
app.include_router(memory.router)
