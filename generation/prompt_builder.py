"""Dựng messages cho LLM từ các file trong prompts/ (không hard-code prompt trong code)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from retrieval.store import Source


class PromptBuilder:
    def __init__(self, prompts_dir: Path, status_note: Callable[[str], str] | None = None):
        self.dir = prompts_dir
        self.status_note = status_note or (lambda _doc_id: "")

    def _read(self, name: str) -> str:
        return (self.dir / name).read_text(encoding="utf-8").strip()

    def source_block(self, sources: list[Source]) -> str:
        parts = []
        for i, s in enumerate(sources, start=1):
            note = self.status_note(s.doc_id)
            status = f"\n(Tình trạng: {note})" if note else ""
            parts.append(f"[{i}] {s.header}{status}\n{s.text}")
        return "\n\n".join(parts)

    def answer_messages(self, question: str, sources: list[Source], missing_refs: list[str] | None = None) -> list[dict]:
        user = f"NGUỒN:\n{self.source_block(sources)}\n\n"
        if missing_refs:
            user += "LƯU Ý: Kho văn bản không có " + "; ".join(missing_refs) + ". Hãy nói rõ điều này với người dùng.\n\n"
        user += f"CÂU HỎI: {question}\nTRẢ LỜI:"
        return [{"role": "system", "content": self._read("answer_vi.md")}, {"role": "user", "content": user}]

    def condense_messages(self, history: list[dict], question: str) -> list[dict]:
        lines = []
        for h in history:
            who = "Người dùng" if h.get("role") == "user" else "Trợ lý"
            lines.append(f"{who}: {h.get('content', '').strip()[:600]}")
        prompt = self._read("condense_vi.md").format(history="\n".join(lines), question=question)
        return [{"role": "user", "content": prompt}]

    def no_rag_messages(self, question: str) -> list[dict]:
        return [{"role": "system", "content": self._read("no_rag_vi.md")}, {"role": "user", "content": question}]

    def refusal_text(self) -> str:
        return self._read("refuse_vi.md")
