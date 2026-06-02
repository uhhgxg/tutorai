"""出题 API —— 根据知识点生成练习题"""

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from app.models import QuizRequest
from app.services.llm_client import chat_stream, build_quiz_messages
from app.services.document_parser import parse_document

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.post("/generate")
def generate_quiz(req: QuizRequest):
    """根据文本内容生成练习题（流式输出）"""
    messages = build_quiz_messages(req.content, req.question_count)

    def generate():
        for token in chat_stream(messages, temperature=0.8, max_tokens=3000):
            yield token

    return StreamingResponse(generate(), media_type="text/plain")


@router.post("/generate-from-file")
async def generate_quiz_from_file(
    file: UploadFile = File(...),
    question_count: int = 3,
):
    """上传文档，自动提取内容并生成练习题"""
    if not file.filename:
        content = "未提供文件"
    else:
        try:
            content = parse_document(file.filename, await file.read())
            content = content[:4000]
        except ValueError as e:
            content = f"文件解析失败: {e}"

    messages = build_quiz_messages(content, question_count)

    def generate():
        for token in chat_stream(messages, temperature=0.8, max_tokens=3000):
            yield token

    return StreamingResponse(generate(), media_type="text/plain")
