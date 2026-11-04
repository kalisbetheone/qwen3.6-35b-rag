"""Truy xuất sparse BM25 (thư viện bm25s) trên văn bản đã tách từ tiếng Việt."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from retrieval.text import make_tokenizer


class BM25Index:
    def __init__(self, tokenizer: str = "underthesea"):
        self.tokenizer_name = tokenizer
        self.tokenize = make_tokenizer(tokenizer)
        self.retriever = None
        self.vocab: dict[str, int] = {}

    def build(self, texts: list[str]) -> BM25Index:
        import bm25s

        corpus = [self.tokenize(t) or ["<rỗng>"] for t in texts]
        self.retriever = bm25s.BM25()
        self.retriever.index(corpus, show_progress=False)
        self.vocab = self.retriever.vocab_dict
        return self

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.retriever.save(str(path), show_progress=False)
        (path / "tokenizer.json").write_text(json.dumps({"tokenizer": self.tokenizer_name}), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        import bm25s

        info = json.loads((path / "tokenizer.json").read_text(encoding="utf-8"))
        obj = cls(info["tokenizer"])
        obj.retriever = bm25s.BM25.load(str(path), show_progress=False)
        obj.vocab = obj.retriever.vocab_dict
        return obj

    def scores(self, query: str) -> np.ndarray:
        toks = [t for t in self.tokenize(query) if t in self.vocab]
        n = self.retriever.scores["num_docs"]
        if not toks:
            return np.zeros(n, dtype=np.float32)
        return np.asarray(self.retriever.get_scores(toks), dtype=np.float32)

    def search(self, query: str, top_k: int = 30, mask: np.ndarray | None = None) -> list[tuple[int, float]]:
        s = self.scores(query)
        if mask is not None:
            s = np.where(mask, s, -np.inf)
        k = min(top_k, int(np.isfinite(s).sum()))
        if k <= 0:
            return []
        idx = np.argpartition(-s, k - 1)[:k]
        idx = idx[np.argsort(-s[idx])]
        return [(int(i), float(s[i])) for i in idx if s[i] > 0]
