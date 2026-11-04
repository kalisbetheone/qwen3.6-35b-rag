"""Cross-encoder reranker (mặc định BAAI/bge-reranker-v2-m3). Điểm trả về đã qua sigmoid, thuộc [0, 1]."""
from __future__ import annotations

from common.config import ModelsCfg
from retrieval.dense import resolve_device


class Reranker:
    def __init__(self, cfg: ModelsCfg):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.cfg = cfg
        self.torch = torch
        self.device = resolve_device(cfg.device)
        self.tokenizer = AutoTokenizer.from_pretrained(cfg.rerank_model)
        dtype = torch.float16 if cfg.fp16 and self.device.startswith("cuda") else torch.float32
        self.model = AutoModelForSequenceClassification.from_pretrained(cfg.rerank_model, torch_dtype=dtype)
        self.model.to(self.device).eval()

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        out: list[float] = []
        bs = self.cfg.rerank_batch_size
        with self.torch.inference_mode():
            for i in range(0, len(pairs), bs):
                batch = pairs[i:i + bs]
                enc = self.tokenizer([q for q, _ in batch], [p for _, p in batch], padding=True, truncation=True,
                                     max_length=self.cfg.rerank_max_length, return_tensors="pt").to(self.device)
                logits = self.model(**enc).logits.view(-1).float()
                out.extend(self.torch.sigmoid(logits).cpu().tolist())
        return out

    def score(self, query: str, passages: list[str]) -> list[float]:
        return self.score_pairs([(query, p) for p in passages]) if passages else []
