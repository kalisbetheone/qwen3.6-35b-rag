"""Ablation truy xuất: BM25 · Dense bge-m3 · Dense DEk21 · Hybrid RRF · Hybrid + rerank · + direct lookup.

    python -m eval.run_retrieval                          # split test
    python -m eval.run_retrieval --split dev --calibrate  # dò ngưỡng τ trên dev
    python -m eval.run_retrieval --configs bm25 hybrid_rrf

Quy ước: một kết quả được tính đúng nếu trúng cùng Điều với gold_chunk_ids (so ở mức Điều).
Câu should_refuse không tính vào Recall/MRR/nDCG; chúng dùng để đo tỷ lệ "không đủ căn cứ" đúng khi có rerank.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from common.config import load_config, model_slug  # noqa: E402
from eval.common import RESULTS, ROOT, dedupe, load_qa, mrr_at, ndcg_at, parent_of, percentile, recall_at, write_csv

DEK21 = "huyydangg/DEk21_hcmute_embedding"
CONFIGS = {
    "bm25":          dict(use_router=False, use_bm25=True,  use_dense=False, use_rerank=False),
    "dense_bge-m3":  dict(use_router=False, use_bm25=False, use_dense=True,  use_rerank=False),
    "dense_dek21":   dict(use_router=False, use_bm25=False, use_dense=True,  use_rerank=False, embed_model=DEK21),
    "hybrid_rrf":    dict(use_router=False, use_bm25=True,  use_dense=True,  use_rerank=False),
    "hybrid_rerank": dict(use_router=False, use_bm25=True,  use_dense=True,  use_rerank=True),
    "full_router":   dict(use_router=True,  use_bm25=True,  use_dense=True,  use_rerank=True),
}


class Cache:
    """Giữ model đã nạp giữa các cấu hình (bge-m3, reranker chỉ nạp một lần)."""

    def __init__(self):
        self.encoders, self.dense, self.bm25, self.store, self.reranker = {}, {}, {}, {}, None

    def pipeline(self, name: str, spec: dict, base_threshold: float | None):
        from retrieval.bm25 import BM25Index
        from retrieval.dense import DenseEncoder, DenseIndex
        from retrieval.pipeline import RetrievalPipeline
        from retrieval.store import ChunkStore

        embed = spec.get("embed_model", "BAAI/bge-m3")
        ov = {f"retrieval.{k}": v for k, v in spec.items() if k.startswith("use_")}
        ov["models.embed_model"] = embed  # preset theo model (vd DEk21) do load_config tự áp
        if base_threshold is not None:
            ov["retrieval.rerank_threshold"] = base_threshold
        cfg = load_config(overrides=ov)
        idx = cfg.index_path
        if not (idx / "meta.parquet").exists():
            raise FileNotFoundError(f"chưa có index {idx} (build: EMBED_MODEL={embed} python scripts/build_index.py)")
        key = str(idx)
        if key not in self.store:
            self.store[key] = ChunkStore.load(idx)
            self.bm25[key] = BM25Index.load(idx / "bm25")
        dense = enc = None
        if spec["use_dense"]:
            if key not in self.dense:
                self.dense[key] = DenseIndex.load(idx / "dense.npy")
            if embed not in self.encoders:
                self.encoders[embed] = DenseEncoder(cfg.models)
            dense, enc = self.dense[key], self.encoders[embed]
        rr = None
        if spec["use_rerank"]:
            if self.reranker is None:
                from retrieval.rerank import Reranker

                self.reranker = Reranker(cfg.models)
            rr = self.reranker
        return RetrievalPipeline(cfg, self.store[key], self.bm25[key] if spec["use_bm25"] else None, dense, enc, rr)


def evaluate(pipe, qa: list[dict], levels: list[str]) -> tuple[dict, list[dict]]:
    per, lat = [], []
    for q in qa:
        t = time.perf_counter()
        res = pipe.retrieve(q["question"], levels)
        ms = (time.perf_counter() - t) * 1000
        lat.append(ms)
        ranked = dedupe(parent_of(c) for c in res.ranked_ids)
        gold = {parent_of(c) for c in q.get("gold_chunk_ids", [])}
        row = {"id": q["id"], "group": q.get("group"), "should_refuse": bool(q.get("should_refuse")),
               "route": res.route, "no_evidence": res.no_evidence,
               "top_score": round(res.ranked_scores[0], 4) if res.ranked_scores else None,
               "top5": " ".join(ranked[:5]), "gold": " ".join(sorted(gold)), "latency_ms": round(ms, 1)}
        if not row["should_refuse"]:
            row.update(recall5=recall_at(gold, ranked, 5), mrr10=mrr_at(gold, ranked, 10),
                       ndcg10=ndcg_at(gold, ranked, 10))
        per.append(row)
    ins = [r for r in per if not r["should_refuse"]]
    outs = [r for r in per if r["should_refuse"]]
    mean = lambda k: round(sum(r[k] for r in ins) / len(ins), 4) if ins else None  # noqa: E731
    summary = {"n_questions": len(ins), "recall@5": mean("recall5"), "mrr@10": mean("mrr10"),
               "ndcg@10": mean("ndcg10"),
               "no_evidence_on_out_of_scope": round(sum(r["no_evidence"] for r in outs) / len(outs), 4) if outs else None,
               "no_evidence_on_in_scope": round(sum(r["no_evidence"] for r in ins) / len(ins), 4) if ins else None,
               "latency_p50_ms": round(percentile(lat, 50), 1), "latency_p95_ms": round(percentile(lat, 95), 1)}
    return summary, per


def calibrate(per: list[dict]) -> list[dict]:
    """Quét τ: câu trong phạm vi phải có top_score ≥ τ, câu ngoài phạm vi phải < τ. Chọn τ có balanced acc cao nhất."""
    ins = [r["top_score"] or 0 for r in per if not r["should_refuse"]]
    outs = [r["top_score"] or 0 for r in per if r["should_refuse"]]
    rows = []
    for i in range(5, 96, 5):
        tau = i / 100
        tpr = sum(s >= tau for s in ins) / len(ins) if ins else 0
        tnr = sum(s < tau for s in outs) / len(outs) if outs else 0
        rows.append({"tau": tau, "answer_rate_in_scope": round(tpr, 3), "refuse_rate_out_scope": round(tnr, 3),
                     "balanced_acc": round((tpr + tnr) / 2, 3)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", default=str(ROOT / "eval" / "qa_set.jsonl"))
    ap.add_argument("--split", default="test", help="dev | test | all")
    ap.add_argument("--configs", nargs="*", default=list(CONFIGS))
    ap.add_argument("--role", default="giang_vien")
    ap.add_argument("--calibrate", action="store_true", help="dò τ cho hybrid_rerank (đặt τ=0 khi chạy)")
    args = ap.parse_args()

    qa = load_qa(Path(args.qa), args.split)
    print(f"{len(qa)} câu ({args.split})")
    levels = load_config().allowed_levels(args.role)
    cache, rows = Cache(), []
    for name in args.configs:
        spec = CONFIGS[name]
        try:
            pipe = cache.pipeline(name, spec, 0.0 if args.calibrate else None)
        except FileNotFoundError as e:
            print(f"[bỏ qua] {name}: {e}")
            continue
        summary, per = evaluate(pipe, qa, levels)
        summary = {"config": name, "embed_model": model_slug(spec.get("embed_model", "BAAI/bge-m3")) if spec["use_dense"] else "",
                   "split": args.split, **summary}
        rows.append(summary)
        write_csv(RESULTS / f"retrieval_per_question_{name}.csv", per)
        print({k: v for k, v in summary.items() if k != "split"})
        if args.calibrate and spec["use_rerank"] and not spec["use_router"]:
            cal = calibrate(per)
            write_csv(RESULTS / "tau_calibration.csv", cal)
            best = max(cal, key=lambda r: r["balanced_acc"])
            print(f"τ tốt nhất trên {args.split}: {best} -> đặt retrieval.rerank_threshold trong config.yaml")
    if not args.calibrate:
        write_csv(RESULTS / "retrieval.csv", rows)
        print(f"-> {RESULTS / 'retrieval.csv'}")


if __name__ == "__main__":
    main()
