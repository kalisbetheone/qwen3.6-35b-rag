"""Sinh bộ câu hỏi NHÁP từ chunk bằng LLM -> eval/qa_draft.jsonl. BẠN PHẢI DUYỆT VÀ SỬA TỪNG CÂU,
rồi lưu thành eval/qa_set.jsonl (đặt "reviewed": true cho câu đã duyệt).

    python scripts/gen_qa_draft.py                  # cần LLM đang chạy (LLM_BASE_URL)
    python scripts/gen_qa_draft.py --seed 7 --dev 15

Mỗi dòng: id, question, group, gold_chunk_ids[], gold_answer_short, should_refuse, split, reviewed
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from generation.llm_client import make_llm  # noqa: E402
from retrieval.store import ChunkStore  # noqa: E402

QUOTA = {"tra_cuu": 20, "tong_hop": 10, "doi_thuong": 10, "hieu_luc": 5, "ngoai_pham_vi": 10, "tham_chieu": 5}

PROMPTS = {
    "tra_cuu": "Từ đoạn văn bản pháp luật dưới đây, viết MỘT câu hỏi tra cứu cụ thể mà câu trả lời nằm trọn trong đoạn "
               "(ưu tiên hỏi về con số, điều kiện, thời hạn, đối tượng). Không nhắc số Điều trong câu hỏi.",
    "tong_hop": "Từ Điều luật dưới đây (gồm nhiều khoản), viết MỘT câu hỏi đòi hỏi tổng hợp thông tin từ ít nhất hai khoản. "
                "Không nhắc số Điều trong câu hỏi.",
    "doi_thuong": "Từ đoạn văn bản dưới đây, viết MỘT câu hỏi bằng ngôn ngữ đời thường như một sinh viên hoặc giảng viên "
                  "trẻ hỏi (không dùng thuật ngữ pháp lý, không nhắc số hiệu văn bản), câu trả lời nằm trong đoạn.",
    "hieu_luc": "Từ đoạn văn bản dưới đây (quy định về hiệu lực / thay thế văn bản), viết MỘT câu hỏi về việc văn bản nào "
                "còn hay hết hiệu lực, từ ngày nào, thay thế văn bản nào.",
}
FORMAT = ('\n\nTrả về đúng một đối tượng JSON, không giải thích: {"question": "...", "answer": "câu trả lời ngắn, '
          'trích đúng con số trong đoạn"}\n\nĐOẠN VĂN BẢN:\n')
OUT_OF_SCOPE = ("Viết 15 câu hỏi tiếng Việt ngắn, đa dạng, về các lĩnh vực hành chính KHÔNG liên quan tới khoa học, "
                "công nghệ, đổi mới sáng tạo hay giáo dục đại học (ví dụ thuế, giao thông, đất đai, hôn nhân, bảo hiểm xã hội). "
                'Trả về JSON: {"questions": ["...", "..."]}')


def ask_json(llm, prompt: str) -> dict | None:
    try:
        text = llm.complete([{"role": "user", "content": prompt}], max_tokens=600, temperature=0.4)
    except Exception as e:
        print("  LLM lỗi:", e)
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dev", type=int, default=15, help="số câu dành cho dev, còn lại test")
    ap.add_argument("--out", default=str(ROOT / "eval" / "qa_draft.jsonl"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    cfg = load_config()
    store = ChunkStore.load(cfg.index_path)
    llm = make_llm(cfg.llm)
    pub = [c for c in store.chunks if c.access_level == "public" and c.n_tokens >= 25]
    current = [c for c in pub if c.hieu_luc == "con_hieu_luc"] or pub
    rng.shuffle(current)
    rows: list[dict] = []

    def add(group, q, gold, ans, refuse=False):
        rows.append({"id": f"{group}_{sum(r['group'] == group for r in rows) + 1:02d}", "question": q.strip(),
                     "group": group, "gold_chunk_ids": gold, "gold_answer_short": (ans or "").strip(),
                     "should_refuse": refuse, "reviewed": False})

    pool = iter(current)
    for group in ("tra_cuu", "doi_thuong"):
        while sum(r["group"] == group for r in rows) < QUOTA[group]:
            c = next(pool, None)
            if c is None:
                break
            j = ask_json(llm, PROMPTS[group] + FORMAT + c.text_for_embed)
            if j and j.get("question"):
                add(group, j["question"], [c.chunk_id], j.get("answer"))
                print(f"  {group}: {j['question']}")

    multi = [a for a in store.articles.values() if a.access_level == "public" and len(store.by_article.get(a.article_id, [])) >= 2]
    rng.shuffle(multi)
    for a in multi[: QUOTA["tong_hop"] * 2]:
        if sum(r["group"] == "tong_hop" for r in rows) >= QUOTA["tong_hop"]:
            break
        j = ask_json(llm, PROMPTS["tong_hop"] + FORMAT + f"{a.header}\n{a.text[:6000]}")
        if j and j.get("question"):
            add("tong_hop", j["question"], [store.ids[i] for i in store.by_article[a.article_id]], j.get("answer"))

    eff = [c for c in pub if re.search(r"hiệu lực|thay thế|bãi bỏ", (c.ten_dieu or "") + c.text_display, re.I)]
    for c in eff[: QUOTA["hieu_luc"] * 2]:
        if sum(r["group"] == "hieu_luc" for r in rows) >= QUOTA["hieu_luc"]:
            break
        j = ask_json(llm, PROMPTS["hieu_luc"] + FORMAT + c.text_for_embed)
        if j and j.get("question"):
            add("hieu_luc", j["question"], [c.chunk_id], j.get("answer"))

    j = ask_json(llm, OUT_OF_SCOPE) or {}
    for q in (j.get("questions") or [])[: QUOTA["ngoai_pham_vi"]]:
        add("ngoai_pham_vi", q, [], "Các văn bản hiện có không quy định.", refuse=True)

    arts = [a for a in store.articles.values() if a.access_level == "public" and a.hieu_luc == "con_hieu_luc"]
    for a in rng.sample(arts, min(QUOTA["tham_chieu"], len(arts))):
        label = store.docs[a.doc_id].label
        add("tham_chieu", f"Điều {a.dieu} {label} quy định gì?", [store.ids[i] for i in store.by_article[a.article_id]],
            a.ten_dieu or "")

    # chia dev/test theo tỷ lệ trong từng nhóm
    by_group: dict[str, list[dict]] = {}
    for r in rows:
        by_group.setdefault(r["group"], []).append(r)
    n_dev_total = 0
    for items in by_group.values():
        n_dev = round(len(items) * args.dev / max(len(rows), 1))
        for k, r in enumerate(items):
            r["split"] = "dev" if k < n_dev else "test"
        n_dev_total += n_dev
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"\n{len(rows)} câu nháp ({n_dev_total} dev) -> {args.out}\nHÃY DUYỆT TAY rồi lưu thành eval/qa_set.jsonl")


if __name__ == "__main__":
    main()
