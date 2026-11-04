from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=32)  # None = tạo hội thoại mới
    doc_filter: list[str] | None = None
    mode: Literal["answer", "search"] = "answer"


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    doc_filter: list[str] | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class FeedbackRequest(BaseModel):
    query_id: str = Field(max_length=64)
    rating: Literal[1, -1]
    comment: str | None = Field(default=None, max_length=2000)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class DocumentOut(BaseModel):
    doc_id: str
    so_hieu: str
    loai: str
    label: str
    ten: str
    ngay_ban_hanh: str
    hieu_luc: str
    thay_the_boi: str
    access_level: str
    url_nguon: str
    n_articles: int
    n_chunks: int
    source: str
    uploaded_by: str


class SearchResponse(BaseModel):
    results: list[dict]
    nearest: list[dict]
    no_evidence: bool
    route: str
    latency_ms: dict[str, float]
