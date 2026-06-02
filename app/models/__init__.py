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
