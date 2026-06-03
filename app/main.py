"""TutorAI — FastAPI 应用入口

一个基于 AI 的智能学习助手，支持:
- 多轮对话辅导
- 文档上传与检索问答 (RAG)
- 自动生成练习题
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import chat, document, quiz, pages
from app.database import get_db, get_all_chunks
from app.services.retriever import rebuild_index


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化数据库和检索索引"""
    conn = get_db()
    try:
        all_chunks = get_all_chunks(conn)
        if all_chunks:
            rebuild_index(all_chunks)
    finally:
        conn.close()
    yield


app = FastAPI(
    title="TutorAI",
    description="AI 智能学习助手 — 支持对话辅导、文档问答、出题测试",
    version="1.0.0",
    lifespan=lifespan,
)

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 注册路由
app.include_router(pages.router)
app.include_router(chat.router)
app.include_router(document.router)
app.include_router(quiz.router)
