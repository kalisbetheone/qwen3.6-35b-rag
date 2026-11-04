"""Có RAG vs không RAG: cùng LLM, cùng bộ câu hỏi.

    python -m eval.run_e2e                       # cả hai cấu hình trên split test
    python -m eval.run_e2e --configs rag --label fp8   # chạy lại với LLM khác (đặt LLM_MODEL/LLM_BASE_URL)

Đầu ra (eval/results/):
  e2e_answers_<cfg>.jsonl   toàn bộ câu trả lời + chỉ số tự động
  e2e_grading_<cfg>.csv     BẠN CHẤM TAY cột score (0/1/2) rồi chạy make_report.py
  e2e.csv, latency.csv      bảng tóm tắt
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from common.config import load_config  # noqa: E402
from eval.common import RESULTS, ROOT, load_qa, percentile, read_csv, write_csv
from generation.verify import REFUSAL_PHRASES, parse_cites, verify  # noqa: E402
from retrieval.router import Router  # noqa: E402

EXTRA_REFUSAL = ("không chắc", "không có thông tin", "không rõ", "chưa có thông tin", "không thể xác định")


def is_refusal(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in REFUSAL_PHRASES + EXTRA_REFUSAL)


def reference_checks(answer: str, router: Router, store) -> dict:
    """Bịa điều khoản: trích 'Điều N <văn bản trong kho>' mà Điều đó không tồn tại.
    Lỗi thời: lấy một Điều/Khoản cụ thể của văn bản đã hết hiệu lực (vd 'Khoản 2 Điều 11 NĐ 109/2022') làm căn cứ
    mà không nói rõ văn bản đó đã hết hiệu lực. Chỉ nhắc tên văn bản cũ (vd khi trích điều khoản chuyển tiếp của
    văn bản mới) không tính."""
    hits = router.route(answer)
    fabricated = [f"Điều {h.dieu} {store.doc_label(h.doc_id)}" for h in hits if h.article_id not in store.articles]
    expired = [h for h in hits if store.docs[h.doc_id].hieu_luc == "het_hieu_luc"]
    low = answer.lower()
    flagged = "hết hiệu lực" in low or "được thay thế" in low
    return {"fabricated_refs": fabricated, "cites_expired_doc": bool(expired) and not flagged}


def run_config(name: str, service, qa: list[dict], role: str) -> list[dict]:
    router = Router(service.pipeline.store.docs.values())
    store = service.pipeline.store
    out = []
    for i, q in enumerate(qa, 1):
        t = time.perf_counter()
        if name == "no_rag":
            try:
                ans = service.llm.complete(service.prompts.no_rag_messages(q["question"]))
                err = None
            except Exception as e:
                ans, err = "", str(e)[:200]
            # cùng bộ hậu kiểm như RAG (không có nguồn nên chỉ có cờ unsupported); grounding để trống
            row = {"answer": ans, "latency_ms": {"generate": (time.perf_counter() - t) * 1000}, "error": err,
                   "citations_used": [], "grounding_score": None, "flags": verify(ans, []).flags,
                   "no_evidence": False, "sources": []}
        else:
            r = service.answer(q["question"], user_role=role)
            row = {"answer": r.get("answer", ""), "latency_ms": r.get("latency_ms", {}),
                   "error": r.get("message") if r.get("event") == "error" else None,
                   "citations_used": r.get("citations_used", []), "grounding_score": r.get("grounding_score"),
                   "flags": r.get("flags", []), "no_evidence": r.get("no_evidence", False), "route": r.get("route"),
                   "invalid_citations": r.get("invalid_citations", []),
                   "sources": [s["chunk_id"] for s in r.get("sources", [])]}
        row.update({"id": q["id"], "question": q["question"], "group": q.get("group"),
                    "should_refuse": bool(q.get("should_refuse")), "gold_answer_short": q.get("gold_answer_short", ""),
                    "gold_chunk_ids": q.get("gold_chunk_ids", []), "config": name,
                    "refused": row["no_evidence"] or is_refusal(row["answer"]),
                    "n_labels": len(parse_cites(row["answer"])), **reference_checks(row["answer"], router, store)})
        out.append(row)
        ms = row["latency_ms"].get("total", row["latency_ms"].get("generate", 0))
        print(f"[{name}] {i}/{len(qa)} {q['id']} refused={row['refused']} {ms:.0f}ms")
    return out


def summarize(name: str, rows: list[dict], label: str) -> dict:
    ins = [r for r in rows if not r["should_refuse"]]
    outs = [r for r in rows if r["should_refuse"]]
    rate = lambda xs, f: round(sum(f(r) for r in xs) / len(xs), 4) if xs else None  # noqa: E731
    gs = [r["grounding_score"] for r in ins if r["grounding_score"] is not None]
    return {
        "config": name, "label": label, "n": len(rows),
        "correct_refusal_out_of_scope": rate(outs, lambda r: r["refused"]),
        "false_refusal_in_scope": rate(ins, lambda r: r["refused"]),
        "fabricated_ref_rate": rate(rows, lambda r: bool(r["fabricated_refs"])),
        "cites_expired_doc_rate": rate(rows, lambda r: r["cites_expired_doc"]),
        "answers_with_citation": rate(ins, lambda r: r["n_labels"] > 0),
        "mean_grounding_score": round(sum(gs) / len(gs), 4) if gs else None,
        "unsupported_sentence_rate": rate(ins, lambda r: any(f["type"] == "unsupported" for f in r["flags"])),
        "errors": sum(1 for r in rows if r.get("error")),
    }


def latency_rows(name: str, rows: list[dict], label: str) -> list[dict]:
    stages = sorted({k for r in rows for k in r["latency_ms"]})
    return [{"config": name, "label": label, "stage": s,
             "p50_ms": round(percentile([r["latency_ms"][s] for r in rows if s in r["latency_ms"]], 50), 1),
             "p95_ms": round(percentile([r["latency_ms"][s] for r in rows if s in r["latency_ms"]], 95), 1)}
            for s in stages]


def _kept(prev: dict, row: dict, key: str) -> str:
    """Giữ điểm đã chấm tay nếu câu trả lời không đổi so với lần chạy trước."""
    old = prev.get(row["id"], {})
    return old.get(key, "") if old.get("answer") == row["answer"] else ""


def _merge_csv(path: Path, new: list[dict], keys: tuple[str, ...]) -> None:
    """Ghi đè các dòng cùng (config,label,...) để chạy lại từng cấu hình không mất cấu hình khác."""
    old = read_csv(path) if path.exists() and path.stat().st_size else []
    sig = {tuple(str(r.get(k)) for k in keys) for r in new}
    write_csv(path, [r for r in old if tuple(str(r.get(k)) for k in keys) not in sig] + new)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", default=str(ROOT / "eval" / "qa_set.jsonl"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--configs", nargs="*", default=["no_rag", "rag"])
    ap.add_argument("--label", default="q4", help="nhãn biến thể LLM, vd q4 | fp8")
    ap.add_argument("--role", default="giang_vien")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    from generation.service import RAGService

    cfg = load_config()
    service = RAGService.from_config(cfg)
    qa = load_qa(Path(args.qa), args.split)[: args.limit]
    summaries, lats = [], []
    for name in args.configs:
        rows = run_config(name, service, qa, args.role)
        tag = f"{name}_{args.label}"
        with (RESULTS / f"e2e_answers_{tag}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        grading = RESULTS / f"e2e_grading_{tag}.csv"
        prev = {r["id"]: r for r in read_csv(grading)} if grading.exists() and grading.stat().st_size else {}
        write_csv(grading, [{"id": r["id"], "group": r["group"], "should_refuse": r["should_refuse"],
                             "question": r["question"], "gold_answer_short": r["gold_answer_short"], "answer": r["answer"],
                             "score": _kept(prev, r, "score"),
                             "citation_ok": _kept(prev, r, "citation_ok"),
                             "note": ""} for r in rows])
        summaries.append(summarize(name, rows, args.label))
        lats.extend(latency_rows(name, rows, args.label))
        print(summaries[-1])
    _merge_csv(RESULTS / "e2e.csv", summaries, ("config", "label"))
    _merge_csv(RESULTS / "latency.csv", lats, ("config", "label", "stage"))
    print(f"-> {RESULTS}/e2e.csv, latency.csv; chấm tay cột 'score' trong e2e_grading_*.csv")


if __name__ == "__main__":
    main()
