"""Pipeline truy xuất: direct lookup → BM25 ‖ dense → RRF → rerank (ngưỡng τ) → parent expansion."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from common.config import AppConfig
from ingest.chunker import heuristic_tokens
from retrieval.bm25 import BM25Index
from retrieval.fusion import rrf
from retrieval.router import RouteHit, Router
from retrieval.store import ChunkStore, Source


@dataclass
class RetrievalResult:
    sources: list[Source]
    no_evidence: bool
    route: str  # direct | search
    nearest: list[Source] = field(default_factory=list)  # khi no_evidence: 3 điều khoản gần nhất
    ranked_ids: list[str] = field(default_factory=list)  # thứ hạng đầy đủ trước ngưỡng (cho đánh giá)
    ranked_scores: list[float] = field(default_factory=list)  # điểm tương ứng (rerank nếu có, không thì RRF)
    missing_refs: list[str] = field(default_factory=list)  # tham chiếu tường minh không tồn tại trong kho
    timings: dict[str, float] = field(default_factory=dict)


class RetrievalPipeline:
    def __init__(self, cfg: AppConfig, store: ChunkStore, bm25: BM25Index | None = None,
                 dense=None, encoder=None, reranker=None):
        self.cfg = cfg
        self.store = store
        self.bm25 = bm25
        self.dense = dense
        self.encoder = encoder
        self.reranker = reranker
        self.router = Router(store.docs.values(), cfg.retrieval.router_default_doc_id)
        self._lock = threading.RLock()  # retrieve() và swap() không chạy chồng nhau

    def swap(self, store: ChunkStore, bm25: BM25Index | None, dense) -> None:
        """Thay index đang phục vụ (sau khi thêm/xoá văn bản) mà không khởi động lại server."""
        with self._lock:
            self.store, self.bm25, self.dense = store, bm25, dense
            self.router = Router(store.docs.values(), self.cfg.retrieval.router_default_doc_id)

    # ------------------------------------------------------------ nạp
    @classmethod
    def load(cls, cfg: AppConfig, index_dir: Path | None = None, reranker=None) -> RetrievalPipeline:
        """Nạp index đã build (scripts/build_index.py). Dense/rerank chỉ nạp nếu bật trong config."""
        r = cfg.retrieval
        index_dir = index_dir or cfg.index_path
        if not (index_dir / "meta.parquet").exists():
            raise FileNotFoundError(f"Chưa có index tại {index_dir} — chạy scripts/build_index.py trước")
        store = ChunkStore.load(index_dir)
        bm25 = BM25Index.load(index_dir / "bm25") if r.use_bm25 else None
        dense = encoder = None
        if r.use_dense:
            from retrieval.dense import DenseEncoder, DenseIndex

            if not (index_dir / "dense.npy").exists():
                raise FileNotFoundError(f"{index_dir}/dense.npy không có — build lại index có dense hoặc đặt USE_DENSE=false")
            dense = DenseIndex.load(index_dir / "dense.npy")
            if dense.matrix.shape[0] != len(store.chunks):
                raise ValueError(f"dense.npy có {dense.matrix.shape[0]} vector nhưng index có {len(store.chunks)} chunk — build lại index")
            encoder = DenseEncoder(cfg.models)
        if r.use_rerank and reranker is None:
            from retrieval.rerank import Reranker

            reranker = Reranker(cfg.models)
        return cls(cfg, store, bm25, dense, encoder, reranker if r.use_rerank else None)

    # ------------------------------------------------------------ direct lookup
    def _resolve_hit(self, hit: RouteHit, mask: np.ndarray) -> list[Source]:
        idxs = [i for i in self.store.by_article.get(hit.article_id, []) if mask[i]]
        if not idxs:
            return []
        if hit.khoan:
            sel = [i for i in idxs if self.store.chunks[i].khoan in hit.khoan]
            if hit.diem:
                sel = [i for i in sel if (self.store.chunks[i].diem or hit.diem).startswith(hit.diem)] or sel
            if sel:
                return [self.store.chunk_source(i, 1.0, "direct") for i in sel]
        src = self.store.article_source(hit.article_id, 1.0, "direct")
        return [src] if src else []

    # ------------------------------------------------------------ chính
    def retrieve(self, query: str, allowed_levels: list[str], doc_filter: list[str] | None = None,
                 top_k: int | None = None) -> RetrievalResult:
        with self._lock:
            return self._retrieve(query, allowed_levels, doc_filter, top_k)

    def _retrieve(self, query: str, allowed_levels: list[str], doc_filter: list[str] | None,
                  top_k: int | None) -> RetrievalResult:
        r = self.cfg.retrieval
        top_k = top_k or r.top_k
        t0 = time.perf_counter()
        mask = self.store.mask(allowed_levels, doc_filter)
        missing: list[str] = []

        if r.use_router:
            hits = self.router.route(query, doc_filter)
            direct: list[Source] = []
            for h in hits:
                found = self._resolve_hit(h, mask)
                if found:
                    direct.extend(found)
                elif h.doc_id in self.store.docs:
                    missing.append(f"Điều {h.dieu} {self.store.doc_label(h.doc_id)}")
            if direct:
                direct = direct[: max(top_k, len(hits))]
                ms = (time.perf_counter() - t0) * 1000
                ids = [c for s in direct for c in s.chunk_ids]
                return RetrievalResult(direct, False, "direct", ranked_ids=ids, ranked_scores=[1.0] * len(ids),
                                       missing_refs=missing, timings={"retrieve": ms, "rerank": 0.0})

        rankings: list[list[int]] = []
        if self.bm25 is not None:
            rankings.append([i for i, _ in self.bm25.search(query, r.bm25_top_k, mask)])
        if self.dense is not None and self.encoder is not None:
            q = self.encoder.encode_query(query)
            rankings.append([i for i, _ in self.dense.search(q, r.dense_top_k, mask)])
        fused = rrf(rankings, k=r.rrf_k, top_n=r.fusion_top_k)
        t1 = time.perf_counter()

        cands = [int(i) for i, _ in fused]
        penalty = np.array([r.expired_penalty if self.store.chunks[i].hieu_luc == "het_hieu_luc" else 1.0 for i in cands])
        if self.reranker is not None and cands:
            raw = self.reranker.score(query, [self.store.chunks[i].text_for_embed for i in cands])
            scores = np.asarray(raw) * penalty
            order = np.argsort(-scores, kind="stable")
            ranked = [(cands[j], float(scores[j])) for j in order]
            passing = [(i, s) for i, s in ranked if s >= r.rerank_threshold]
            retriever = "hybrid+rerank"
        else:
            fscores = np.array([s for _, s in fused]) * penalty
            order = np.argsort(-fscores, kind="stable")
            ranked = [(cands[j], float(fscores[j])) for j in order]
            passing = ranked
            retriever = "hybrid" if len(rankings) > 1 else ("bm25" if self.bm25 is not None else "dense")
        t2 = time.perf_counter()

        ranked_ids = [self.store.ids[i] for i, _ in ranked]
        ranked_scores = [s for _, s in ranked]
        timings = {"retrieve": (t1 - t0) * 1000, "rerank": (t2 - t1) * 1000}
        if not passing:
            nearest = [self.store.chunk_source(i, s, retriever) for i, s in ranked[:3]]
            return RetrievalResult([], True, "search", nearest, ranked_ids, ranked_scores, missing, timings)

        sources = [self.store.chunk_source(i, s, retriever) for i, s in passing[:top_k]]
        if r.parent_expansion:
            sources = self._expand_parents(sources)
        return RetrievalResult(sources, False, "search", ranked_ids=ranked_ids, ranked_scores=ranked_scores,
                               missing_refs=missing, timings=timings)

    # ------------------------------------------------------------ parent expansion
    def _expand_parents(self, sources: list[Source]) -> list[Source]:
        groups: dict[str, list[Source]] = {}
        for s in sources:
            groups.setdefault(s.parent_article_id, []).append(s)
        out: list[Source] = []
        done: set[str] = set()
        for s in sources:
            pid = s.parent_article_id
            if pid in done:
                continue
            group = groups[pid]
            if len(group) < 2:
                out.append(s)
                continue
            done.add(pid)
            best = max(x.score for x in group)
            ids = [c for x in group for c in x.chunk_ids]
            art = self.store.articles.get(pid)
            if art and heuristic_tokens(art.text) <= self.cfg.retrieval.parent_max_tokens:
                merged = self.store.article_source(pid, best, s.retriever, chunk_ids=ids)
            else:  # Điều quá dài: chỉ nối các phần trúng, theo thứ tự trong văn bản
                group = sorted(group, key=lambda x: self.store.pos[x.chunk_ids[0]])
                merged = Source(**{**group[0].to_dict(), "chunk_ids": ids, "score": best, "khoan": None, "diem": None,
                                   "text": "\n…\n".join(x.text for x in group),
                                   "citation_label": art.citation_label if art else group[0].citation_label})
            merged.extra["expanded_from"] = len(group)
            out.append(merged)
        return out
