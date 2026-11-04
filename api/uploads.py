"""Thêm/xoá văn bản từ giao diện: lưu file -> parse (Điều/Khoản, hoặc chia theo đề mục) -> chunk -> cập nhật index.

Chạy nền theo job để request trả về ngay; giao diện hỏi GET /api/jobs/{id} để biết tiến độ.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path

from common.config import AppConfig
from common.schema import DocMeta, load_registry, save_registry
from ingest.chunker import Chunker
from ingest.parser import parse_file
from retrieval.indexer import IndexUpdater

log = logging.getLogger("vilex")


class UploadError(Exception):
    pass


class UploadManager:
    def __init__(self, cfg: AppConfig, updater: IndexUpdater):
        self.cfg = cfg
        self.updater = updater
        self.jobs: dict[str, dict] = {}
        self._reg_lock = threading.Lock()

    # ------------------------------------------------------------ thêm
    def submit(self, username: str, filename: str, data: bytes, form: dict) -> dict:
        ext = Path(filename).suffix.lower()
        if ext == ".doc":
            raise UploadError("File .doc (Word 97–2003) chưa hỗ trợ — mở bằng Word và lưu lại thành .docx")
        if ext not in self.cfg.upload.extensions:
            raise UploadError(f"Chỉ hỗ trợ {', '.join(self.cfg.upload.extensions)}")
        if len(data) > self.cfg.upload.max_mb * 1024 * 1024:
            raise UploadError(f"File quá lớn (tối đa {self.cfg.upload.max_mb:g} MB)")
        if not data:
            raise UploadError("File rỗng")

        doc_id = f"up-{uuid.uuid4().hex[:8]}"
        ten = (form.get("ten") or Path(filename).stem).strip()[:300]
        meta = DocMeta(
            doc_id=doc_id, so_hieu=(form.get("so_hieu") or "").strip(), loai=form.get("loai") or "Tài liệu",
            ten=ten, ngay_ban_hanh=(form.get("ngay_ban_hanh") or "").strip(), hieu_luc=form.get("hieu_luc") or "con_hieu_luc",
            co_quan=(form.get("co_quan") or "").strip(), url_nguon=(form.get("url_nguon") or "").strip(),
            access_level=form.get("access_level") or "public", file=f"{doc_id}{ext}", source="upload",
            uploaded_by=username, ghi_chu=f"Tải lên {time.strftime('%d/%m/%Y %H:%M')} — {Path(filename).name}",
        )
        raw = self.cfg.uploads_raw_dir
        raw.mkdir(parents=True, exist_ok=True)
        (raw / meta.file).write_bytes(data)

        job = {"id": uuid.uuid4().hex[:12], "status": "queued", "doc_id": doc_id, "filename": Path(filename).name,
               "message": "Đang chờ xử lý…", "created_at": time.time()}
        self.jobs[job["id"]] = job
        threading.Thread(target=self._run, args=(job, meta), daemon=True).start()
        return job

    def _run(self, job: dict, meta: DocMeta) -> None:
        path = self.cfg.uploads_raw_dir / meta.file
        try:
            job.update(status="running", message="Đang đọc và phân tích cấu trúc văn bản…")
            doc = parse_file(path, fallback=True)
            chunks, arts = Chunker(self.cfg.chunking).chunk_document(meta, doc)
            if not chunks:
                raise UploadError("Không đọc được nội dung chữ (file scan/ảnh?). Hãy dùng bản có lớp text.")
            job.update(message=f"Đã tách {len(arts)} {doc.unit.lower()}, {len(chunks)} đoạn — đang cập nhật chỉ mục…",
                       n_articles=len(arts), n_chunks=len(chunks), unit=doc.unit)
            self.updater.add_document(meta, chunks, arts)
            with self._reg_lock:
                docs = load_registry(self.cfg.uploads_registry, source="upload")
                save_registry(self.cfg.uploads_registry, docs + [meta])
            job.update(status="done", message=f"Đã thêm “{meta.ten}”: {len(arts)} {doc.unit.lower()}, {len(chunks)} đoạn.")
            log.info("upload %s ok: %d chunks", meta.doc_id, len(chunks))
        except Exception as e:  # báo lỗi rõ ràng cho người dùng, dọn file
            log.exception("upload %s lỗi", meta.doc_id)
            path.unlink(missing_ok=True)
            msg = str(e) if isinstance(e, (UploadError, ValueError)) else "Không xử lý được file này."
            job.update(status="error", message=msg)

    def get(self, job_id: str) -> dict | None:
        return self.jobs.get(job_id)

    # ------------------------------------------------------------ xoá
    def delete(self, doc_id: str) -> None:
        store = self.updater.pipeline.store
        d = store.docs.get(doc_id)
        if d is None:
            raise UploadError("Không tìm thấy văn bản")
        if d.source != "upload":
            raise UploadError("Chỉ xoá được văn bản tải lên qua giao diện; văn bản kho gốc quản lý bằng registry.csv")
        self.updater.remove_document(doc_id)
        with self._reg_lock:
            docs = [x for x in load_registry(self.cfg.uploads_registry, source="upload") if x.doc_id != doc_id]
            save_registry(self.cfg.uploads_registry, docs)
        if d.file:
            (self.cfg.uploads_raw_dir / d.file).unlink(missing_ok=True)
