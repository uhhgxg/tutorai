"""出题 API —— 根据知识点生成练习题"""

from sqlite3 import Connection

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.db.engine import get_db
from app.models import QuizKbRequest, QuizRequest, QuizResultResponse, QuizSaveRequest
from app.services.quiz_service import QuizService

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.post("/generate")
def generate_quiz(
    req: QuizRequest,
    user: dict = Depends(get_current_user),
):
    """根据文本内容生成练习题（流式输出）"""
    svc = QuizService(user["id"])
    return StreamingResponse(
        svc.generate(req.content, req.question_count, req.question_type),
        media_type="text/plain",
    )


@router.post("/generate-from-kb")
def generate_quiz_from_kb(
    req: QuizKbRequest,
    user: dict = Depends(get_current_user),
):
    """从知识库中检索知识点并生成练习题（流式输出）"""
    svc = QuizService(user["id"])
    return StreamingResponse(
        svc.generate_from_kb(req.topic, req.doc_id, req.question_count, req.question_type),
        media_type="text/plain",
    )


@router.post("/generate-from-file")
async def generate_quiz_from_file(
    file: UploadFile = File(...),
    question_count: int = 3,
    question_type: str = "choice",
    user: dict = Depends(get_current_user),
):
    """上传文档，自动提取内容并生成练习题"""
    svc = QuizService(user["id"])
    return StreamingResponse(
        await svc.generate_from_file(file, question_count, question_type),
        media_type="text/plain",
    )


@router.post("/results", response_model=QuizResultResponse)
def save_result(
    req: QuizSaveRequest,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = QuizService(user["id"])
    return svc.save_result(conn, req.title, req.result_text, req.question_count)


@router.get("/results", response_model=list[QuizResultResponse])
def list_results(
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = QuizService(user["id"])
    return svc.list_results(conn)


@router.get("/results/{result_id}")
def get_result(
    result_id: str,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = QuizService(user["id"])
    result = svc.get_result(conn, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="结果不存在")
    return result


@router.delete("/results/{result_id}")
def delete_result(
    result_id: str,
    conn: Connection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    svc = QuizService(user["id"])
    if not svc.delete_result(conn, result_id):
        raise HTTPException(status_code=404, detail="结果不存在")
    return {"ok": True}
