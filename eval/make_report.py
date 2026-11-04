"""Gộp eval/results/*.csv -> 2 biểu đồ + report.md. Mọi con số trong bài lấy từ đây.

    python -m eval.make_report
"""
from __future__ import annotations

import time

from eval.common import RESULTS, read_csv


def md_table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "\n_(chưa có dữ liệu)_\n"
    out = ["", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(_fmt(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out) + "\n"


def _fmt(v) -> str:
    try:
        f = float(v)
        return f"{f:.3f}" if f != int(f) or "." in str(v) else str(int(f))
    except (TypeError, ValueError):
        return str(v) if v not in (None, "None") else "—"


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def grading_summary() -> list[dict]:
    """Điểm chấm tay 0/1/2 trong e2e_grading_<cfg>_<label>.csv."""
    out = []
    for p in sorted(RESULTS.glob("e2e_grading_*.csv")):
        rows = read_csv(p)
        scored = [r for r in rows if str(r.get("score", "")).strip() in {"0", "1", "2"}]
        if not scored:
            out.append({"file": p.name, "graded": f"0/{len(rows)}"})
            continue
        s = [int(r["score"]) for r in scored]
        cit = [r for r in scored if str(r.get("citation_ok", "")).strip() in {"0", "1"}]
        out.append({"file": p.name, "graded": f"{len(scored)}/{len(rows)}",
                    "mean_score_0_2": sum(s) / len(s), "fully_correct_rate": sum(x == 2 for x in s) / len(s),
                    "citation_precision": (sum(int(r["citation_ok"]) for r in cit) / len(cit)) if cit else None})
    return out


def chart_retrieval(rows: list[dict]) -> str | None:
    if not rows:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = [r["config"] for r in rows]
    vals = [_f(r.get("recall@5")) or 0 for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4), dpi=200)
    bars = ax.bar(names, vals, color=["#9aa5b1"] * (len(vals) - 1) + ["#1f4e79"])
    ax.bar_label(bars, labels=[f"{v:.2f}" for v in vals], fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Recall@5 (mức Điều)")
    ax.set_title("Ablation truy xuất")
    ax.spines[["top", "right"]].set_visible(False)
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    path = RESULTS / "fig_retrieval_recall5.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def chart_e2e(rows: list[dict], grades: list[dict]) -> str | None:
    if not rows:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    acc = {g["file"].removeprefix("e2e_grading_").removesuffix(".csv"): g.get("fully_correct_rate") for g in grades}
    metrics = [("Trả lời đúng hoàn toàn", lambda r: acc.get(f"{r['config']}_{r['label']}")),
               ("Từ chối đúng (ngoài phạm vi)", lambda r: _f(r.get("correct_refusal_out_of_scope"))),
               ("Bịa điều khoản", lambda r: _f(r.get("fabricated_ref_rate"))),
               ("Viện dẫn văn bản hết hiệu lực", lambda r: _f(r.get("cites_expired_doc_rate")))]
    labels = [f"{r['config']} ({r['label']})" for r in rows]
    x = np.arange(len(metrics))
    w = 0.8 / len(rows)
    fig, ax = plt.subplots(figsize=(9, 4), dpi=200)
    for i, r in enumerate(rows):
        vals = [(f(r) or 0) for _, f in metrics]
        b = ax.bar(x + i * w - 0.4 + w / 2, vals, w, label=labels[i])
        ax.bar_label(b, labels=[f"{v:.0%}" for v in vals], fontsize=8)
    ax.set_xticks(x, [m for m, _ in metrics])
    ax.set_ylim(0, 1.1)
    ax.legend(frameon=False)
    ax.set_title("LLM không RAG và có RAG trên cùng bộ câu hỏi")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = RESULTS / "fig_e2e_compare.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def main() -> None:
    load = lambda n: read_csv(RESULTS / n) if (RESULTS / n).exists() and (RESULTS / n).stat().st_size else []  # noqa: E731
    retr, e2e, lat = load("retrieval.csv"), load("e2e.csv"), load("latency.csv")
    tau = load("tau_calibration.csv")
    grades = grading_summary()
    f1, f2 = chart_retrieval(retr), chart_e2e(e2e, grades)

    parts = [f"# Kết quả thử nghiệm ViLex-ANND\n\n_Tự sinh lúc {time.strftime('%d/%m/%Y %H:%M')} từ eval/results/. "
             "Không sửa tay số liệu trong file này._\n",
             "## 1. Ablation truy xuất\n\nQuy ước: tính đúng nếu trúng cùng Điều với đáp án chuẩn. "
             "Câu ngoài phạm vi không tính vào Recall/MRR/nDCG.\n",
             md_table(retr, ["config", "embed_model", "n_questions", "recall@5", "mrr@10", "ndcg@10",
                             "no_evidence_on_out_of_scope", "latency_p50_ms", "latency_p95_ms"])]
    if f1:
        parts.append(f"\n![Recall@5]({f1})\n")
    if tau:
        best = max(tau, key=lambda r: _f(r["balanced_acc"]) or 0)
        parts.append(f"\nNgưỡng τ chọn trên tập dev: **{best['tau']}** (balanced accuracy {best['balanced_acc']}).\n")
    parts += ["\n## 2. Có RAG và không có RAG\n\nTự động đo:\n", md_table(e2e, [
        "config", "label", "n", "correct_refusal_out_of_scope", "false_refusal_in_scope", "fabricated_ref_rate",
        "cites_expired_doc_rate", "answers_with_citation", "mean_grounding_score", "unsupported_sentence_rate", "errors"]),
        "\nChấm tay (thang 0/1/2):\n", md_table(grades, ["file", "graded", "mean_score_0_2", "fully_correct_rate",
                                                       "citation_precision"])]
    if f2:
        parts.append(f"\n![So sánh]({f2})\n")
    parts += ["\n## 3. Độ trễ theo giai đoạn\n\n", md_table(lat, ["config", "label", "stage", "p50_ms", "p95_ms"])]
    (RESULTS / "report.md").write_text("".join(parts), encoding="utf-8")
    print(f"-> {RESULTS / 'report.md'}")


if __name__ == "__main__":
    main()
