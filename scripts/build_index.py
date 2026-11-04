"""chunks.jsonl -> index/<embed_model>/{meta.parquet, articles.jsonl, docs.json, bm25/, dense.npy, build_info.json}

    python scripts/build_index.py              # đầy đủ (cần GPU cho dense, chạy trên Colab)
    python scripts/build_index.py --no-dense   # chỉ BM25 + metadata (laptop/CPU)
    EMBED_MODEL=huyydangg/DEk21_hcmute_embedding python scripts/build_index.py   # index cho model so sánh
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import load_config  # noqa: E402
from ingest.run_ingest import load_all_docs  # noqa: E402
from retrieval.bm25 import BM25Index  # noqa: E402
from retrieval.store import ChunkStore  # noqa: E402


def chunks_sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def is_stale(cfg, out: Path, need_dense: bool) -> bool:
    """Index thiếu, thiếu dense, hoặc build từ chunks.jsonl khác bản hiện tại."""
    info = out / "build_info.json"
    if not info.exists() or (need_dense and not (out / "dense.npy").exists()):
        return True
    return json.loads(info.read_text(encoding="utf-8")).get("chunks_sha1") != chunks_sha1(cfg.path(cfg.paths.chunks))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--no-dense", action="store_true")
    ap.add_argument("--out", help="ghi đè thư mục index")
    ap.add_argument("--if-stale", action="store_true", help="chỉ build khi chunks.jsonl đã đổi so với index hiện có")
    args = ap.parse_args()

    cfg = load_config(args.config)
    out = Path(args.out) if args.out else cfg.index_path
    if args.if_stale and not is_stale(cfg, out, need_dense=not args.no_dense):
        print(f"Index {out} đã khớp chunks.jsonl — bỏ qua")
        return
    docs = load_all_docs(cfg)
    store = ChunkStore.from_files(cfg.path(cfg.paths.chunks), cfg.path(cfg.paths.articles), docs)
    if not store.chunks:
        sys.exit("chunks.jsonl rỗng — chạy python -m ingest.run_ingest trước")
    print(f"{len(store.chunks)} chunk, {len(store.articles)} Điều -> {out}")

    t = time.time()
    store.save(out)
    texts = [c.text_for_embed for c in store.chunks]
    BM25Index(cfg.retrieval.bm25_tokenizer).build(texts).save(out / "bm25")
    print(f"BM25 xong ({time.time() - t:.1f}s)")

    info = {"n_chunks": len(store.chunks), "bm25_tokenizer": cfg.retrieval.bm25_tokenizer, "dense": None,
            "chunks_sha1": chunks_sha1(cfg.path(cfg.paths.chunks)), "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not args.no_dense:
        from retrieval.dense import DenseEncoder, DenseIndex

        t = time.time()
        enc = DenseEncoder(cfg.models)
        DenseIndex(enc.encode_passages(texts)).save(out / "dense.npy")
        info["dense"] = {"model": cfg.models.embed_model, "device": enc.device,
                         "dim": int(enc.model.get_sentence_embedding_dimension() or 0)}
        print(f"Dense xong trên {enc.device} ({time.time() - t:.1f}s)")
    (out / "build_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
