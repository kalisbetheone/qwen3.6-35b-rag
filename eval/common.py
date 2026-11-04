"""Tiện ích dùng chung cho các script đánh giá."""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "eval" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
RE_PARENT = re.compile(r"^(.+?_d[0-9a-z]+)(?:_k\d+)?(?:_[a-z]+(?:-[a-z]+)?)?$")


def parent_of(chunk_id: str) -> str:
    m = RE_PARENT.match(chunk_id)
    return m.group(1) if m else chunk_id


def load_qa(path: Path, split: str | None = None) -> list[dict]:
    # utf-8-sig: file sửa tay bằng Notepad/Excel trên Windows hay có BOM
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    return [r for r in rows if split in (None, "all") or r.get("split", "test") == split]


def dedupe(seq):
    return list(dict.fromkeys(seq))


def recall_at(gold: set[str], ranked: list[str], k: int) -> float:
    return len(gold & set(ranked[:k])) / len(gold) if gold else 0.0


def mrr_at(gold: set[str], ranked: list[str], k: int) -> float:
    for i, x in enumerate(ranked[:k], start=1):
        if x in gold:
            return 1.0 / i
    return 0.0


def ndcg_at(gold: set[str], ranked: list[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, x in enumerate(ranked[:k], start=1) if x in gold)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / idcg if idcg else 0.0


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    i = (len(xs) - 1) * p / 100
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = dedupe(k for r in rows for k in r)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel mở đúng tiếng Việt
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
