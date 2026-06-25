"""页面路由 —— 渲染 HTML 模板"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html", {"conv_id": ""})


@router.get("/chat/{conv_id}", response_class=HTMLResponse)
async def chat_page_with_id(request: Request, conv_id: str):
    return templates.TemplateResponse(request, "chat.html", {"conv_id": conv_id})


@router.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request):
    return templates.TemplateResponse(request, "documents.html")


@router.get("/quiz", response_class=HTMLResponse)
async def quiz_page(request: Request):
    return templates.TemplateResponse(request, "quiz.html")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.get("/404", response_class=HTMLResponse)
async def not_found_page(request: Request):
    return templates.TemplateResponse(request, "404.html")


@router.get("/403", response_class=HTMLResponse)
async def forbidden_page(request: Request):
    return templates.TemplateResponse(request, "403.html")
