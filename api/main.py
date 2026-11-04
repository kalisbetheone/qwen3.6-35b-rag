"""FastAPI: /api/* + phục vụ frontend/dist — một tunnel, một URL khi demo.

    uvicorn api.main:app --host 0.0.0.0 --port 7860
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.auth import User
from api.conversations import ConversationStore
from api.deps import Services, current_user, get_services, init_services, uploader
from api.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationRename,
    DocumentOut,
    FeedbackRequest,
    LoginRequest,
    SearchRequest,
    SearchResponse,
)
from api.uploads import UploadError
from common.config import load_config
from generation.service import source_payload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vilex")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_services()
    yield


cfg = load_config()
app = FastAPI(title="ViLex-ANND", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=cfg.api.cors_origins, allow_methods=["*"], allow_headers=["*"])


def _rag(s: Services):
    if s.rag is None:
        raise HTTPException(503, detail=f"Hệ thống chưa sẵn sàng: {s.error}")
    return s.rag


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _user_out(s: Services, u: User) -> dict:
    return {**u.to_dict(), "can_upload": u.role in s.cfg.upload.allowed_roles}


# ---------------------------------------------------------------- đăng nhập


@app.post("/api/auth/login")
def login(req: LoginRequest, s: Services = Depends(get_services)):
    user = s.users.authenticate(req.username, req.password)
    if user is None:
        raise HTTPException(401, detail="Tên đăng nhập hoặc mật khẩu không đúng. Vui lòng thử lại.")
    return {"token": s.signer.issue(user), "user": _user_out(s, user)}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user), s: Services = Depends(get_services)):
    return _user_out(s, user)


# ---------------------------------------------------------------- hội thoại


@app.get("/api/conversations")
def list_conversations(user: User = Depends(current_user), s: Services = Depends(get_services)):
    return s.conversations.list(user.username)


@app.post("/api/conversations")
def create_conversation(req: ConversationCreate, user: User = Depends(current_user), s: Services = Depends(get_services)):
    c = s.conversations.create(user.username, req.title or "")
    return {k: c[k] for k in ("id", "title", "created_at", "updated_at")}


@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str, user: User = Depends(current_user), s: Services = Depends(get_services)):
    c = s.conversations.get(user.username, conv_id)
    if c is None:
        raise HTTPException(404, detail="Không tìm thấy hội thoại")
    return c


@app.patch("/api/conversations/{conv_id}")
def rename_conversation(conv_id: str, req: ConversationRename, user: User = Depends(current_user),
                        s: Services = Depends(get_services)):
    c = s.conversations.rename(user.username, conv_id, req.title)
    if c is None:
        raise HTTPException(404, detail="Không tìm thấy hội thoại")
    return {k: c[k] for k in ("id", "title", "created_at", "updated_at")}


@app.delete("/api/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, user: User = Depends(current_user), s: Services = Depends(get_services)):
    if not s.conversations.delete(user.username, conv_id):
        raise HTTPException(404, detail="Không tìm thấy hội thoại")
    return Response(status_code=204)


# ---------------------------------------------------------------- hỏi–đáp


@app.post("/api/chat")
def chat(req: ChatRequest, user: User = Depends(current_user), s: Services = Depends(get_services)):
    rag = _rag(s)
    if req.conversation_id:
        conv = s.conversations.get(user.username, req.conversation_id)
        if conv is None:
            raise HTTPException(404, detail="Không tìm thấy hội thoại")
    else:
        conv = s.conversations.create(user.username)
    history = ConversationStore.history(conv, s.cfg.llm.max_history_turns)
    conv_id = conv["id"]

    def gen() -> Iterator[str]:
        sources: list[dict] = []
        try:
            for name, data in rag.events(req.question, history, user.role, req.doc_filter, req.mode,
                                         username=user.username):
                data = {**data, "conversation_id": conv_id}
                if name == "sources":
                    sources = data["sources"]
                elif name == "done":
                    s.conversations.append_turn(user.username, conv_id, req.question, req.mode, data, sources)
                yield _sse(name, data)
        except Exception:
            log.exception("Lỗi khi xử lý /api/chat")
            yield _sse("error", {"message": "Đã xảy ra lỗi khi xử lý câu hỏi. Vui lòng thử lại.",
                                 "conversation_id": conv_id})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest, user: User = Depends(current_user), s: Services = Depends(get_services)):
    rag = _rag(s)
    res = rag.pipeline.retrieve(req.question, s.cfg.allowed_levels(user.role), req.doc_filter, req.top_k)
    if s.query_log:
        s.query_log({"mode": "search_api", "user": user.username, "role": user.role, "question": req.question,
                     "route": res.route, "chunk_ids": [c for x in res.sources for c in x.chunk_ids],
                     "no_evidence": res.no_evidence})
    return SearchResponse(results=source_payload(res.sources), nearest=source_payload(res.nearest),
                          no_evidence=res.no_evidence, route=res.route,
                          latency_ms={k: round(v, 1) for k, v in res.timings.items()})


@app.post("/api/feedback", status_code=204)
def feedback(req: FeedbackRequest, user: User = Depends(current_user), s: Services = Depends(get_services)):
    if s.feedback_log:
        s.feedback_log({**req.model_dump(), "user": user.username})
    return Response(status_code=204)


# ---------------------------------------------------------------- kho văn bản


@app.get("/api/documents", response_model=list[DocumentOut])
def documents(user: User = Depends(current_user), s: Services = Depends(get_services)):
    store = _rag(s).pipeline.store
    n_art = Counter(a.doc_id for a in store.articles.values())
    n_chunk = Counter(c.doc_id for c in store.chunks)
    out = []
    for d in store.visible_docs(s.cfg.allowed_levels(user.role)):
        if n_chunk[d.doc_id] == 0:
            continue  # có trong registry nhưng chưa ingest
        out.append(DocumentOut(doc_id=d.doc_id, so_hieu=d.so_hieu, loai=d.loai, label=d.label, ten=d.ten,
                               ngay_ban_hanh=d.ngay_ban_hanh, hieu_luc=d.hieu_luc, thay_the_boi=d.thay_the_boi,
                               access_level=d.access_level, url_nguon=d.url_nguon, n_articles=n_art[d.doc_id],
                               n_chunks=n_chunk[d.doc_id], source=d.source, uploaded_by=d.uploaded_by))
    return out


@app.get("/api/documents/{doc_id}/articles")
def document_articles(doc_id: str, user: User = Depends(current_user), s: Services = Depends(get_services)):
    """Mục lục một văn bản: danh sách Điều (hoặc Phần) theo thứ tự, gom theo Chương."""
    store = _rag(s).pipeline.store
    d = store.docs.get(doc_id)
    if d is None or d.access_level not in s.cfg.allowed_levels(user.role):
        raise HTTPException(404, detail="Không tìm thấy văn bản")
    arts = [a for a in store.articles.values() if a.doc_id == doc_id]
    return {"doc": {"doc_id": d.doc_id, "label": d.label, "ten": d.ten, "loai": d.loai, "hieu_luc": d.hieu_luc,
                    "ngay_ban_hanh": d.ngay_ban_hanh, "url_nguon": d.url_nguon, "status_note": store.status_note(doc_id)},
            "articles": [{"dieu": a.dieu, "ten_dieu": a.ten_dieu, "chuong": a.chuong, "ten_chuong": a.ten_chuong,
                          "citation_label": a.citation_label} for a in arts]}


@app.get("/api/article/{doc_id}/{dieu}")
def article(doc_id: str, dieu: str, user: User = Depends(current_user), s: Services = Depends(get_services)):
    store = _rag(s).pipeline.store
    a = store.articles.get(f"{doc_id}_d{dieu.lower()}")
    # không có quyền -> cũng trả 404 để không lộ sự tồn tại của văn bản nội bộ
    if a is None or a.access_level not in s.cfg.allowed_levels(user.role):
        raise HTTPException(404, detail="Không tìm thấy nội dung này")
    d = a.model_dump()
    d["status_note"] = store.status_note(doc_id)
    return d


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    loai: str = Form("Tài liệu"), so_hieu: str = Form(""), ten: str = Form(""), ngay_ban_hanh: str = Form(""),
    co_quan: str = Form(""), url_nguon: str = Form(""),
    access_level: Literal["public", "internal"] = Form("public"),
    hieu_luc: Literal["con_hieu_luc", "het_hieu_luc"] = Form("con_hieu_luc"),
    user: User = Depends(uploader), s: Services = Depends(get_services),
):
    _rag(s)
    data = await file.read()
    form = dict(loai=loai, so_hieu=so_hieu, ten=ten, ngay_ban_hanh=ngay_ban_hanh, co_quan=co_quan,
                url_nguon=url_nguon, access_level=access_level, hieu_luc=hieu_luc)
    try:
        return s.uploads.submit(user.username, file.filename or "tai-lieu", data, form)
    except UploadError as e:
        raise HTTPException(400, detail=str(e)) from e


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user: User = Depends(uploader), s: Services = Depends(get_services)):
    job = s.uploads.get(job_id) if s.uploads else None
    if job is None:
        raise HTTPException(404, detail="Không tìm thấy tác vụ")
    return job


@app.delete("/api/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, user: User = Depends(uploader), s: Services = Depends(get_services)):
    _rag(s)
    try:
        s.uploads.delete(doc_id)
    except UploadError as e:
        raise HTTPException(400, detail=str(e)) from e
    return Response(status_code=204)


# ---------------------------------------------------------------- công khai


@app.get("/api/meta")
def meta(s: Services = Depends(get_services)):
    store = s.rag.pipeline.store if s.rag else None
    updated = ""
    info = s.cfg.index_path / "build_info.json"
    if info.exists():  # đọc lại mỗi lần: thêm/xoá văn bản cập nhật file này
        built = json.loads(info.read_text(encoding="utf-8")).get("built_at", "")
        if len(built) >= 10:
            updated = f"{built[8:10]}/{built[5:7]}/{built[0:4]}"
    return {"suggested_questions": s.cfg.suggested_questions, "updated_at": updated,
            "n_documents": len([d for d in store.docs.values() if d.access_level == "public"]) if store else 0,
            "n_articles": len([a for a in store.articles.values() if a.access_level == "public"]) if store else 0}


def _gpu_info() -> dict:
    try:
        import torch

        if not torch.cuda.is_available():
            return {"available": False}
        free, total = torch.cuda.mem_get_info()
        return {"available": True, "name": torch.cuda.get_device_name(0),
                "mem_used_gb": round((total - free) / 1e9, 2), "mem_total_gb": round(total / 1e9, 2),
                "this_process_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)}
    except Exception:
        return {"available": False}


@app.get("/api/health")
def health(s: Services = Depends(get_services)):
    r = s.cfg.retrieval
    out = {"status": "ok", "error": s.error, "gpu": _gpu_info(),
           "retrieval": {"router": r.use_router, "bm25": r.use_bm25, "dense": r.use_dense, "rerank": r.use_rerank,
                         "embed_model": s.cfg.models.embed_model if r.use_dense else None,
                         "rerank_model": s.cfg.models.rerank_model if r.use_rerank else None,
                         "rerank_threshold": r.rerank_threshold},
           "llm": {"provider": s.cfg.llm.provider, "model": s.cfg.llm.model, "ok": False}}
    if s.rag is None:
        out["status"] = "error"
        return out
    out["index"] = {"n_chunks": len(s.rag.pipeline.store.chunks), "n_articles": len(s.rag.pipeline.store.articles),
                    "path": str(s.cfg.index_path), **s.build_info}
    out["llm"]["ok"] = s.rag.llm.health()
    if not out["llm"]["ok"]:
        out["status"] = "degraded"
    return out


# Frontend tĩnh — mount sau cùng để không che /api/*
_dist = cfg.path(cfg.paths.frontend_dist)
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
