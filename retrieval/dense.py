"""Dense retrieval: encode bằng sentence-transformers, cosine trên vector đã L2-normalize.

Mọi khác biệt giữa các model embedding (tiền tố query:/passage:, input đã tách từ) đóng gói ở đây,
nên đổi model chỉ cần đổi config.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from common.config import ModelsCfg


def resolve_device(device: str) -> str:
    if device.startswith("cuda"):
        try:
            import torch

            if torch.cuda.is_available():
                return device
        except ImportError:
            pass
        return "cpu"
    return device


class DenseEncoder:
    def __init__(self, cfg: ModelsCfg):
        from sentence_transformers import SentenceTransformer

        self.cfg = cfg
        self.device = resolve_device(cfg.device)
        self.model = SentenceTransformer(cfg.embed_model, device=self.device, trust_remote_code=True)
        self.model.max_seq_length = cfg.embed_max_length
        if cfg.fp16 and self.device.startswith("cuda"):
            self.model.half()
        self._seg = None
        if cfg.embed_word_segment:
            from pyvi import ViTokenizer

            self._seg = ViTokenizer.tokenize

    def _prep(self, texts: list[str], prefix: str) -> list[str]:
        if self._seg:
            texts = [self._seg(t) for t in texts]
        return [prefix + t for t in texts]

    def _encode(self, texts: list[str], batch_size: int, progress: bool = False) -> np.ndarray:
        v = self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                              convert_to_numpy=True, show_progress_bar=progress)
        return v.astype(np.float32)

    def encode_passages(self, texts: list[str], progress: bool = True) -> np.ndarray:
        return self._encode(self._prep(texts, self.cfg.embed_passage_prefix), self.cfg.embed_batch_size, progress)

    def encode_query(self, query: str) -> np.ndarray:
        return self._encode(self._prep([query], self.cfg.embed_query_prefix), 1)[0]


class DenseIndex:
    def __init__(self, matrix: np.ndarray):
        self.matrix = matrix.astype(np.float32, copy=False)

    def save(self, path: Path) -> None:
        np.save(path, self.matrix.astype(np.float16))  # float16: nhỏ một nửa, đủ chính xác cho cosine

    @classmethod
    def load(cls, path: Path) -> DenseIndex:
        return cls(np.load(path))

    def search(self, qvec: np.ndarray, top_k: int = 30, mask: np.ndarray | None = None) -> list[tuple[int, float]]:
        s = self.matrix @ qvec
        if mask is not None:
            s = np.where(mask, s, -np.inf)
        k = min(top_k, int(np.isfinite(s).sum()))
        if k <= 0:
            return []
        idx = np.argpartition(-s, k - 1)[:k]
        idx = idx[np.argsort(-s[idx])]
        return [(int(i), float(s[i])) for i in idx]
