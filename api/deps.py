"""Khởi tạo một lần lúc start: index, model embedding/reranker, client LLM, tài khoản, hội thoại, logger."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException

from api.auth import TokenSigner, User, UserStore
from api.conversations import ConversationStore
from api.logging import JsonlLogger
from api.uploads import UploadManager
from common.config import AppConfig, load_config
from generation.service import RAGService
from retrieval.indexer import IndexUpdater

log = logging.getLogger("vilex")


@dataclass
class Services:
    cfg: AppConfig
    users: UserStore
    signer: TokenSigner
    conversations: ConversationStore
    rag: RAGService | None = None
    uploads: UploadManager | None = None
    error: str | None = None
    query_log: JsonlLogger | None = None
    feedback_log: JsonlLogger | None = None
    build_info: dict = field(default_factory=dict)


_services: Services | None = None


def init_services(cfg: AppConfig | None = None) -> Services:
    global _services
    import json

    cfg = cfg or load_config()
    log_dir = cfg.path(cfg.paths.log_dir)
    users = UserStore(cfg.app_path / "users.json")
    users.ensure_seed(cfg)
    s = Services(cfg, users=users, signer=TokenSigner.from_config(cfg),
                 conversations=ConversationStore(cfg.app_path / "conversations"),
                 query_log=JsonlLogger(log_dir / "queries.jsonl"), feedback_log=JsonlLogger(log_dir / "feedback.jsonl"))
    try:
        s.rag = RAGService.from_config(cfg, log=s.query_log)
        s.uploads = UploadManager(cfg, IndexUpdater(cfg, s.rag.pipeline))
        info = cfg.index_path / "build_info.json"
        if info.exists():
            s.build_info = json.loads(info.read_text(encoding="utf-8"))
    except Exception as e:  # thiếu index/model: app vẫn chạy để /api/health báo lỗi rõ ràng
        log.exception("Không khởi tạo được RAGService")
        s.error = f"{type(e).__name__}: {e}"
    _services = s
    return s


def get_services() -> Services:
    if _services is None:
        return init_services()
    return _services


def current_user(authorization: str | None = Header(default=None),
                 s: Services = Depends(get_services)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail="Vui lòng đăng nhập")
    data = s.signer.verify(authorization[7:].strip())
    user = s.users.get(data["sub"]) if data else None
    if user is None:
        raise HTTPException(401, detail="Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại")
    return user


def uploader(user: User = Depends(current_user), s: Services = Depends(get_services)) -> User:
    if user.role not in s.cfg.upload.allowed_roles:
        raise HTTPException(403, detail="Tài khoản của bạn không có quyền thêm dữ liệu")
    return user
