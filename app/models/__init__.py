"""Pydantic 数据模型 —— API 的请求/响应结构"""

from pydantic import BaseModel, Field


# --- Chat ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    id: int | None = None
    conversation_id: str
    role: str
    content: str
    created_at: str | None = None


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


# --- Memory ---
class MemoryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    category: str = Field(default="general", pattern=r"^(profile|goal|preference|progress|general)$")


class MemoryResponse(BaseModel):
    id: str
    category: str
    content: str
    source: str
    created_at: str
    updated_at: str


# --- Document ---
class DocumentResponse(BaseModel):
    id: str
    filename: str
    chunk_count: int
    created_at: str


class DocumentQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)


class DocumentQueryResponse(BaseModel):
    answer: str
    sources: list[str]


# --- Quiz ---
class QuizRequest(BaseModel):
    content: str = Field(..., min_length=50, max_length=5000)
    question_count: int = Field(default=3, ge=1, le=10)
    question_type: str = Field(default="choice", pattern=r"^(choice|true_false|fill_blank|short_answer|mixed)$")


class QuizKbRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500, description="出题的知识点，如'第三章 决策树'")
    doc_id: str | None = Field(default=None, description="限定文档 ID，不传则搜索全部文档")
    question_count: int = Field(default=3, ge=1, le=10)
    question_type: str = Field(default="choice", pattern=r"^(choice|true_false|fill_blank|short_answer|mixed)$")


class QuizSaveRequest(BaseModel):
    title: str = ""
    result_text: str = Field(..., min_length=1)
    question_count: int | None = Field(default=None, ge=0, le=20, description="前端已知的题数，不传则后端自动计数")


class QuizResultResponse(BaseModel):
    id: str
    title: str
    question_count: int = 0
    created_at: str
