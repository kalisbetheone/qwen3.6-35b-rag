"""Client cho server kiểu OpenAI (vLLM, llama.cpp llama-server). Đổi backend chỉ cần đổi LLM_BASE_URL.

provider "echo": không gọi LLM, ghép câu đầu của từng nguồn kèm [n] — dùng để dev/test UI trên laptop.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator

import httpx

from common.config import LLMCfg


class _ThinkFilter:
    """Bỏ khối <think>…</think> nếu model vẫn sinh ra (phòng khi chat template bỏ qua enable_thinking)."""

    def __init__(self):
        self.buf = ""
        self.inside = False
        self.started = False

    def feed(self, delta: str) -> str:
        self.buf += delta
        out = ""
        while self.buf:
            if self.inside:
                end = self.buf.find("</think>")
                if end < 0:
                    self.buf = self.buf[-8:]
                    return out
                self.buf = self.buf[end + len("</think>"):].lstrip()
                self.inside = False
                continue
            start = self.buf.find("<think>")
            if start < 0:
                # giữ lại phần đuôi có thể là đầu thẻ "<think>" bị cắt giữa hai delta
                lt = self.buf.rfind("<")
                cut = lt if lt >= 0 and "<think>".startswith(self.buf[lt:]) else len(self.buf)
                emit, self.buf = self.buf[:cut], self.buf[cut:]
                return out + emit
            out += self.buf[:start]
            self.buf = self.buf[start + len("<think>"):]
            self.inside = True
        return out

    def flush(self) -> str:
        rest, self.buf = ("" if self.inside else self.buf), ""
        return rest


class OpenAICompatLLM:
    def __init__(self, cfg: LLMCfg):
        self.cfg = cfg
        self.client = httpx.Client(base_url=cfg.base_url.rstrip("/"), timeout=cfg.timeout,
                                   headers={"Authorization": f"Bearer {cfg.api_key}"})

    def _body(self, messages: list[dict], stream: bool, max_tokens: int | None, temperature: float | None) -> dict:
        return {
            "model": self.cfg.model,
            "messages": messages,
            "stream": stream,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "chat_template_kwargs": {"enable_thinking": self.cfg.enable_thinking},
        }

    def stream(self, messages: list[dict], sources=None, max_tokens=None, temperature=None) -> Iterator[str]:
        filt = _ThinkFilter()
        with self.client.stream("POST", "/chat/completions",
                                json=self._body(messages, True, max_tokens, temperature)) as r:
            if r.status_code != 200:
                r.read()
                raise RuntimeError(f"LLM trả về HTTP {r.status_code}: {r.text[:300]}")
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue
                if out := filt.feed(delta):
                    yield out
        if rest := filt.flush():
            yield rest

    def complete(self, messages: list[dict], sources=None, max_tokens=None, temperature=None) -> str:
        r = self.client.post("/chat/completions", json=self._body(messages, False, max_tokens, temperature))
        r.raise_for_status()
        text = r.json()["choices"][0]["message"].get("content") or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()

    def health(self) -> bool:
        try:
            return self.client.get("/models", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False


class EchoLLM:
    """Trả lời trích xuất, không cần GPU. Chỉ để kiểm thử luồng API/UI."""

    REFUSAL = "Các văn bản hiện có không quy định về nội dung này."

    def __init__(self, cfg: LLMCfg | None = None):
        self.cfg = cfg

    @staticmethod
    def _first_sentence(text: str) -> str:
        lines = [x for x in text.splitlines() if x.strip()]
        if lines and lines[0].startswith("Điều ") and len(lines) > 1:
            lines = lines[1:]  # bỏ dòng tên Điều
        body = re.sub(r"^(\d+\.|[a-zđ]\))\s*", "", lines[0]) if lines else ""
        m = re.search(r"^(.+?)[.;:](\s|$)", body)
        return (m.group(1) if m else body).strip()

    def _answer(self, sources) -> str:
        if not sources:
            return self.REFUSAL
        parts = [f"- {self._first_sentence(s.text)} [{i}]." for i, s in enumerate(sources[:3], start=1)]
        return "Theo các văn bản tìm được:\n" + "\n".join(parts)

    def stream(self, messages, sources=None, **_) -> Iterator[str]:
        text = self.complete(messages, sources)
        yield from re.findall(r"\S+\s*", text)

    def complete(self, messages, sources=None, **_) -> str:
        if sources is None:  # condense / không RAG: trả lại câu hỏi cuối
            return messages[-1]["content"].rsplit("CÂU HỎI MỚI:", 1)[-1].strip()
        return self._answer(sources)

    def health(self) -> bool:
        return True


def make_llm(cfg: LLMCfg):
    return EchoLLM(cfg) if cfg.provider == "echo" else OpenAICompatLLM(cfg)
