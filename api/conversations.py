"""Lưu hội thoại theo người dùng: appdata/conversations/<username>/<id>.json."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

DEFAULT_TITLE = "Cuộc trò chuyện mới"
_ID = re.compile(r"^[a-f0-9]{12}$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class ConversationStore:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def _dir(self, username: str) -> Path:
        d = self.root / re.sub(r"[^a-z0-9_.-]", "_", username)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, username: str, conv_id: str) -> Path | None:
        if not _ID.match(conv_id):  # chặn path traversal
            return None
        return self._dir(username) / f"{conv_id}.json"

    def _write(self, path: Path, conv: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(conv, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def create(self, username: str, title: str = DEFAULT_TITLE) -> dict:
        conv = {"id": uuid.uuid4().hex[:12], "title": title.strip()[:120] or DEFAULT_TITLE,
                "created_at": _now(), "updated_at": _now(), "messages": []}
        with self._lock:
            self._write(self._path(username, conv["id"]), conv)
        return conv

    def get(self, username: str, conv_id: str) -> dict | None:
        p = self._path(username, conv_id)
        if p is None or not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self, username: str) -> list[dict]:
        out = []
        for p in self._dir(username).glob("*.json"):
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            out.append({"id": c["id"], "title": c["title"], "created_at": c["created_at"],
                        "updated_at": c["updated_at"], "n_messages": len(c["messages"])})
        return sorted(out, key=lambda c: c["updated_at"], reverse=True)

    def rename(self, username: str, conv_id: str, title: str) -> dict | None:
        with self._lock:
            c = self.get(username, conv_id)
            if c is None:
                return None
            c["title"] = title.strip()[:120] or DEFAULT_TITLE
            c["updated_at"] = _now()
            self._write(self._path(username, conv_id), c)
            return c

    def delete(self, username: str, conv_id: str) -> bool:
        p = self._path(username, conv_id)
        if p is None or not p.exists():
            return False
        p.unlink()
        return True

    def append_turn(self, username: str, conv_id: str, question: str, mode: str, answer: dict,
                    sources: list[dict]) -> None:
        """Lưu một lượt hỏi–đáp; tự đặt tiêu đề từ câu hỏi đầu tiên."""
        with self._lock:
            c = self.get(username, conv_id)
            if c is None:
                return
            now = _now()
            c["messages"].append({"id": uuid.uuid4().hex[:12], "role": "user", "content": question,
                                  "mode": mode, "created_at": now})
            c["messages"].append({"id": uuid.uuid4().hex[:12], "role": "assistant",
                                  "content": answer.get("answer", ""), "mode": mode, "created_at": now,
                                  "question": question, "sources": sources, "done": answer})
            if c["title"] == DEFAULT_TITLE:
                c["title"] = question.strip()[:80] + ("…" if len(question.strip()) > 80 else "")
            c["updated_at"] = now
            self._write(self._path(username, conv_id), c)

    @staticmethod
    def history(conv: dict, max_turns: int) -> list[dict]:
        """Các lượt hỏi–đáp đã có căn cứ, dùng để viết lại câu hỏi nối tiếp (condense)."""
        out = []
        for m in conv["messages"]:
            if m["role"] != "assistant" or m.get("mode") != "answer" or (m.get("done") or {}).get("no_evidence"):
                continue
            out += [{"role": "user", "content": m.get("question", "")}, {"role": "assistant", "content": m["content"]}]
        return out[-2 * max_turns:]
