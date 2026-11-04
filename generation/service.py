"""Điều phối một lượt hỏi–đáp: condense → truy xuất → (từ chối | sinh có trích dẫn) → hậu kiểm.

Dùng chung cho API (stream SSE) và script đánh giá (gọi answer()).
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

from common.config import AppConfig
from generation.llm_client import make_llm
from generation.prompt_builder import PromptBuilder
from generation.verify import verify
from retrieval.pipeline import RetrievalPipeline
from retrieval.store import Source

Event = tuple[str, dict]


def source_payload(sources: list[Source], snippet_len: int = 280) -> list[dict]:
    out = []
    for i, s in enumerate(sources, start=1):
        snippet = s.text if len(s.text) <= snippet_len else s.text[:snippet_len].rsplit(" ", 1)[0] + "…"
        out.append({
            "idx": i, "chunk_id": s.chunk_ids[0], "chunk_ids": s.chunk_ids, "citation_label": s.citation_label,
            "header": s.header, "snippet": snippet, "text": s.text, "score": round(s.score, 4),
            "url_nguon": s.url_nguon, "doc_id": s.doc_id, "so_hieu": s.so_hieu, "dieu": s.dieu, "khoan": s.khoan,
            "diem": s.diem, "hieu_luc": s.hieu_luc, "access_level": s.access_level, "retriever": s.retriever,
            "expanded": bool(s.extra.get("expanded_from")),
        })
    return out


class RAGService:
    def __init__(self, cfg: AppConfig, pipeline: RetrievalPipeline, llm, prompts: PromptBuilder,
                 log: Callable[[dict], None] | None = None):
        self.cfg = cfg
        self.pipeline = pipeline
        self.llm = llm
        self.prompts = prompts
        self.log = log

    @classmethod
    def from_config(cls, cfg: AppConfig, index_dir: Path | None = None, log=None) -> RAGService:
        pipeline = RetrievalPipeline.load(cfg, index_dir)
        prompts = PromptBuilder(cfg.path(cfg.paths.prompts_dir), pipeline.store.status_note)
        return cls(cfg, pipeline, make_llm(cfg.llm), prompts, log)

    def _scorer(self):
        rr = self.pipeline.reranker
        return rr.score_pairs if rr is not None else None

    def condense(self, question: str, history: list[dict]) -> str:
        turns = history[-2 * self.cfg.llm.max_history_turns:]
        try:
            q = self.llm.complete(self.prompts.condense_messages(turns, question), max_tokens=200, temperature=0.0)
            q = q.strip().strip('"“”').splitlines()[0].strip() if q.strip() else question
            return q or question
        except Exception:
            return question  # condense lỗi thì dùng câu gốc, không chặn câu trả lời

    def events(self, question: str, history: list[dict] | None = None, user_role: str = "hoc_vien",
               doc_filter: list[str] | None = None, mode: str = "answer", username: str = "") -> Iterator[Event]:
        qid = uuid.uuid4().hex[:12]
        latency: dict[str, float] = {}
        t0 = time.perf_counter()
        standalone = question
        if history and mode == "answer":
            standalone = self.condense(question, history)
            latency["condense"] = (time.perf_counter() - t0) * 1000

        levels = self.cfg.allowed_levels(user_role)
        res = self.pipeline.retrieve(standalone, levels, doc_filter)
        latency["retrieve"] = res.timings.get("retrieve", 0.0)
        latency["rerank"] = res.timings.get("rerank", 0.0)
        sources = source_payload(res.sources)
        yield "sources", {"query_id": qid, "sources": sources, "route": res.route,
                          "standalone_question": standalone, "no_evidence": res.no_evidence}

        done = {"query_id": qid, "answer": "", "citations_used": [], "grounding_score": None, "flags": [],
                "no_evidence": res.no_evidence, "nearest": source_payload(res.nearest), "route": res.route,
                "missing_refs": res.missing_refs, "standalone_question": standalone, "mode": mode}

        if mode == "search":
            latency["generate"] = 0.0
        elif res.no_evidence:
            text = self.prompts.refusal_text()
            yield "token", {"delta": text}
            done["answer"] = text
            latency["generate"] = 0.0
        else:
            t1 = time.perf_counter()
            parts: list[str] = []
            try:
                for delta in self.llm.stream(self.prompts.answer_messages(standalone, res.sources, res.missing_refs),
                                             sources=res.sources):
                    parts.append(delta)
                    yield "token", {"delta": delta}
            except Exception as e:  # mất kết nối LLM: báo lỗi thân thiện, không lộ stacktrace
                self._log(qid, question, standalone, user_role, mode, res, None, latency, error=str(e)[:300],
                          username=username)
                yield "error", {"query_id": qid, "message": "Không kết nối được mô hình ngôn ngữ. Vui lòng thử lại sau ít phút."}
                return
            latency["generate"] = (time.perf_counter() - t1) * 1000
            v = verify("".join(parts).strip(), [f"{s.header}\n{s.text}" for s in res.sources],
                       scorer=self._scorer(), weak_threshold=self.cfg.verify.weak_threshold)
            done.update(answer=v.answer, citations_used=v.citations_used, grounding_score=v.grounding_score,
                        flags=v.flags, invalid_citations=v.invalid_citations, is_refusal=v.is_refusal)

        latency["total"] = (time.perf_counter() - t0) * 1000
        done["latency_ms"] = {k: round(v, 1) for k, v in latency.items()}
        self._log(qid, question, standalone, user_role, mode, res, done, latency, username=username)
        yield "done", done

    def answer(self, question: str, **kw) -> dict:
        """Gọi không stream (cho đánh giá): trả về event done + danh sách nguồn."""
        out: dict = {}
        for name, data in self.events(question, **kw):
            if name == "sources":
                out["sources"] = data["sources"]
            elif name in ("done", "error"):
                out.update(data, event=name)
        return out

    def _log(self, qid, question, standalone, role, mode, res, done, latency, error=None, username="") -> None:
        if not self.log:
            return
        self.log({
            "query_id": qid, "user": username, "role": role, "mode": mode, "question": question, "standalone_question": standalone,
            "route": res.route, "chunk_ids": [c for s in res.sources for c in s.chunk_ids],
            "no_evidence": res.no_evidence, "grounding_score": (done or {}).get("grounding_score"),
            "n_flags": len((done or {}).get("flags", [])), "latency_ms": {k: round(v, 1) for k, v in latency.items()},
            "error": error,
        })
