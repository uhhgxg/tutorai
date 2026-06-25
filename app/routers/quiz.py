"""出题 API —— 根据知识点生成练习题"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from app.models import QuizRequest, QuizSaveRequest, QuizResultResponse
from app.services.llm_client import chat_stream, build_quiz_messages
from app.services.document_parser import parse_document
from app.auth import get_current_user
from app.database import get_db, save_quiz_result as db_save_result
from app.database import list_quiz_results as db_list_results
from app.database import get_quiz_result as db_get_result
from app.database import delete_quiz_result as db_delete_result
from sqlite3 import Connection

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.post("/generate")
def generate_quiz(
    req: QuizRequest,
    user: dict = Depends(get_current_user),
):
    """根据文本内容生成练习题（流式输出）"""
    messages = build_quiz_messages(req.content, req.question_count, req.question_type)

    def generate():
        for token in chat_stream(messages, temperature=0.8, max_tokens=3000):
            yield token

    return StreamingResponse(generate(), media_type="text/plain")


@router.post("/generate-from-file")
async def generate_quiz_from_file(
    file: UploadFile = File(...),
    question_count: int = 3,
    question_type: str = "choice",
    user: dict = Depends(get_current_user),
):
    """上传文档，自动提取内容并生成练习题"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    try:
        content = parse_document(file.filename, await file.read())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not content.strip():
        raise HTTPException(status_code=400, detail="文档内容为空")

    content = content[:4000]
    messages = build_quiz_messages(content, question_count, question_type)

    def generate():
        for token in chat_stream(messages, temperature=0.8, max_tokens=3000):
            yield token

    return StreamingResponse(generate(), media_type="text/plain")


def _get_conn():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


@router.post("/results", response_model=QuizResultResponse)
def save_result(
    req: QuizSaveRequest,
    conn: Connection = Depends(_get_conn),
    user: dict = Depends(get_current_user),
):
    return db_save_result(conn, user["id"], req.title, req.result_text)


@router.get("/results", response_model=list[QuizResultResponse])
def list_results(
    conn: Connection = Depends(_get_conn),
    user: dict = Depends(get_current_user),
):
    return db_list_results(conn, user["id"])


@router.get("/results/{result_id}")
def get_result(
    result_id: str,
    conn: Connection = Depends(_get_conn),
    user: dict = Depends(get_current_user),
):
    result = db_get_result(conn, user["id"], result_id)
    if not result:
        raise HTTPException(status_code=404, detail="结果不存在")
    return result


@router.delete("/results/{result_id}")
def delete_result(
    result_id: str,
    conn: Connection = Depends(_get_conn),
    user: dict = Depends(get_current_user),
):
    if not db_delete_result(conn, user["id"], result_id):
        raise HTTPException(status_code=404, detail="结果不存在")
    return {"ok": True}
