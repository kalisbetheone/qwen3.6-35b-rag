"""Ghi log JSONL (logs/queries.jsonl, logs/feedback.jsonl) — phục vụ đánh giá và kiểm toán."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class JsonlLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def __call__(self, record: dict) -> None:
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **record}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
