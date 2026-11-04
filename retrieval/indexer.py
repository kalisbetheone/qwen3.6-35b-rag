"""Cập nhật index khi thêm/xoá văn bản từ giao diện: BM25 dựng lại (vài chục giây trên CPU),
dense chỉ encode phần mới rồi ghép vào ma trận cũ. Ghi đè index trên đĩa và chunks.jsonl để
lần chạy ingest/build_index sau cho ra cùng kết quả (build_index --if-stale không build lại)."""
from __future__ import annotations

import hashlib
import json
import threading
import time

import numpy as np

from common.config import AppConfig
from common.schema import ArticleRec, Chunk, DocMeta, write_jsonl
from retrieval.bm25 import BM25Index
from retrieval.pipeline import RetrievalPipeline
from retrieval.store import ChunkStore


class IndexUpdater:
    def __init__(self, cfg: AppConfig, pipeline: RetrievalPipeline):
        self.cfg = cfg
        self.pipeline = pipeline
        self._lock = threading.Lock()  # một lần cập nhật tại một thời điểm

    def add_document(self, meta: DocMeta, chunks: list[Chunk], articles: list[ArticleRec]) -> None:
        with self._lock:
            old = self.pipeline.store
            if meta.doc_id in old.docs:
                raise ValueError(f"Văn bản {meta.doc_id} đã có trong kho")
            dense = None
            if self.pipeline.dense is not None and self.pipeline.encoder is not None:
                new_vecs = self.pipeline.encoder.encode_passages([c.text_for_embed for c in chunks], progress=False)
                dense = np.vstack([self.pipeline.dense.matrix, new_vecs]) if len(old.chunks) else new_vecs
            store = ChunkStore(old.chunks + chunks, list(old.articles.values()) + articles,
                               list(old.docs.values()) + [meta])
            self._commit(store, dense)

    def remove_document(self, doc_id: str) -> None:
        with self._lock:
            old = self.pipeline.store
            keep = [i for i, c in enumerate(old.chunks) if c.doc_id != doc_id]
            dense = self.pipeline.dense.matrix[keep] if self.pipeline.dense is not None else None
            store = ChunkStore([old.chunks[i] for i in keep],
                               [a for a in old.articles.values() if a.doc_id != doc_id],
                               [d for d in old.docs.values() if d.doc_id != doc_id])
            self._commit(store, dense)

    def _commit(self, store: ChunkStore, dense_matrix: np.ndarray | None) -> None:
        from retrieval.dense import DenseIndex

        r = self.cfg.retrieval
        bm25 = BM25Index(r.bm25_tokenizer).build([c.text_for_embed for c in store.chunks]) if store.chunks else None
        dense = DenseIndex(dense_matrix) if dense_matrix is not None else None

        out = self.cfg.index_path
        store.save(out)
        if bm25 is not None:
            bm25.save(out / "bm25")
        if dense is not None:
            dense.save(out / "dense.npy")
        elif (out / "dense.npy").exists():
            # chạy không có dense (laptop): vector cũ không còn khớp -> xoá để build_index --if-stale dựng lại
            (out / "dense.npy").unlink()
        chunks_path = self.cfg.path(self.cfg.paths.chunks)
        write_jsonl(chunks_path, store.chunks)
        write_jsonl(self.cfg.path(self.cfg.paths.articles), list(store.articles.values()))

        info_path = out / "build_info.json"
        info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
        info.update(n_chunks=len(store.chunks), chunks_sha1=hashlib.sha1(chunks_path.read_bytes()).hexdigest(),
                    built_at=time.strftime("%Y-%m-%d %H:%M:%S"), updated_by="upload")
        if dense is None:
            info["dense"] = None
        info_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

        self.pipeline.swap(store, bm25 if r.use_bm25 else None, dense if r.use_dense else None)
