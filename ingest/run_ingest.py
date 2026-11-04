"""Đọc data/registry.csv + data/raw/ -> data/processed/chunks.jsonl và articles.jsonl.

    python -m ingest.run_ingest            # cảnh báo nếu số Điều lệch registry
    python -m ingest.run_ingest --strict   # lệch -> exit 1 (dùng làm nghiệm thu T2)
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

from common.config import AppConfig, load_config
from common.schema import DocMeta, load_registry, write_jsonl
from ingest.chunker import Chunker
from ingest.parser import parse_file

EXTS = (".docx", ".pdf", ".txt", ".md")


def find_raw_file(raw_dir: Path, meta: DocMeta) -> Path | list[Path] | None:
    if meta.file:  # nhiều file cách nhau bằng ';' (văn bản đăng trên nhiều số Công báo)
        ps = [raw_dir / f.strip() for f in meta.file.split(";") if f.strip()]
        if not all(p.exists() for p in ps):
            return None
        return ps if len(ps) > 1 else ps[0]
    stems = {meta.doc_id, meta.so_hieu.replace("/", "_"), meta.so_hieu.replace("/", "-")}
    for stem in stems:
        for ext in EXTS:
            p = raw_dir / f"{stem}{ext}"
            if p.exists():
                return p
    return None


def load_all_docs(cfg: AppConfig) -> list[DocMeta]:
    """Danh mục kho gốc (data/registry.csv) + văn bản tải lên (appdata/uploads/registry.csv)."""
    return load_registry(cfg.path(cfg.paths.registry)) + load_registry(cfg.uploads_registry, source="upload")


def _name(path: Path | list[Path]) -> str:
    return f"{path[0].name} (+{len(path) - 1})" if isinstance(path, list) else path.name


def run(cfg: AppConfig, strict: bool = False, only: list[str] | None = None) -> int:
    # văn bản trong kho gốc + văn bản giảng viên tải lên qua giao diện (appdata/uploads)
    sources = [(m, cfg.path(cfg.paths.raw_dir)) for m in load_registry(cfg.path(cfg.paths.registry))]
    sources += [(m, cfg.uploads_raw_dir) for m in load_registry(cfg.uploads_registry, source="upload")]
    chunker = Chunker(cfg.chunking)
    all_chunks, all_articles, problems = [], [], []
    seen_ids: set[str] = set()

    print(f"{'doc_id':<22}{'Điều':>6}{'reg':>6}{'chunk':>7}{'tok TB':>8}{'tok max':>9}  file")
    for meta, raw_dir in sources:
        if only and meta.doc_id not in only:
            continue
        path = find_raw_file(raw_dir, meta)
        if path is None:
            print(f"{meta.doc_id:<22}{'—':>6}{meta.so_dieu or '—':>6}{'—':>7}{'':>8}{'':>9}  (chưa có file trong {raw_dir.name}/)")
            continue
        try:
            doc = parse_file(path, fallback=meta.source == "upload")
        except Exception as e:  # file hỏng / định dạng lạ: báo và đi tiếp
            problems.append(f"{meta.doc_id}: {e}")
            continue
        chunks, arts = chunker.chunk_document(meta, doc)
        uniq = []
        for c in chunks:
            if c.chunk_id in seen_ids:
                problems.append(f"{meta.doc_id}: trùng chunk_id {c.chunk_id} (bỏ bản sau)")
                continue
            seen_ids.add(c.chunk_id)
            uniq.append(c)
        toks = [c.n_tokens for c in uniq] or [0]
        n_art = len(doc.articles)
        mark = ""
        if meta.so_dieu is not None and meta.so_dieu != n_art:
            mark = "  <-- LỆCH"
            problems.append(f"{meta.doc_id}: parse được {n_art} Điều, registry ghi {meta.so_dieu}")
        print(f"{meta.doc_id:<22}{n_art:>6}{meta.so_dieu or '—':>6}{len(uniq):>7}"
              f"{statistics.mean(toks):>8.0f}{max(toks):>9}  {_name(path)}{mark}")
        for w in doc.warnings:
            problems.append(f"{meta.doc_id}: {w}")
        all_chunks.extend(uniq)
        all_articles.extend(arts)

    n = write_jsonl(cfg.path(cfg.paths.chunks), all_chunks)
    write_jsonl(cfg.path(cfg.paths.articles), all_articles)
    toks = [c.n_tokens for c in all_chunks] or [0]
    print(f"\nTổng: {len(all_articles)} Điều, {n} chunk, token TB {statistics.mean(toks):.0f}, "
          f"max {max(toks)} -> {cfg.paths.chunks}")
    if problems:
        print("\nCẢNH BÁO:")
        for p in problems:
            print("  -", p)
    mismatch = any("registry ghi" in p for p in problems)
    return 1 if strict and (mismatch or not all_chunks) else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--only", nargs="*", help="chỉ xử lý các doc_id này")
    args = ap.parse_args()
    sys.exit(run(load_config(args.config), args.strict, args.only))


if __name__ == "__main__":
    main()
