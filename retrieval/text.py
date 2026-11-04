"""Tách từ tiếng Việt cho BM25 (underthesea / pyvi / simple)."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from functools import lru_cache

STOPWORDS = {
    "và", "của", "các", "những", "là", "thì", "mà", "này", "đó", "với", "về", "một", "như", "để", "tại",
    "từ", "do", "bị", "nào", "gì", "ạ", "nhé", "ơi", "vậy", "hả",
}
_WORD = re.compile(r"\w", re.U)


def _clean(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        t = t.lower().strip("_")
        if not t or not _WORD.search(t) or t in STOPWORDS:
            continue
        out.append(t)
        if "_" in t:  # thêm từng âm tiết của từ ghép: chống lệch tách từ giữa câu hỏi và văn bản
            out.extend(s for s in t.split("_") if s and s not in STOPWORDS)
    return out


def _simple(text: str) -> list[str]:
    return re.findall(r"\w+", text)


@lru_cache(maxsize=3)
def make_tokenizer(name: str = "underthesea") -> Callable[[str], list[str]]:
    base: Callable[[str], list[str]]
    if name == "underthesea":
        try:
            from underthesea import word_tokenize

            def base(t: str) -> list[str]:
                return word_tokenize(t, format="text").split()
        except ImportError:
            base = _simple
    elif name == "pyvi":
        try:
            from pyvi import ViTokenizer

            def base(t: str) -> list[str]:
                return ViTokenizer.tokenize(t).split()
        except ImportError:
            base = _simple
    else:
        base = _simple

    def tokenize(text: str) -> list[str]:
        text = unicodedata.normalize("NFC", text)
        # bỏ dấu câu dính liền để tokenizer không tạo token kiểu "khoản_2."
        text = re.sub(r"[\[\]\(\)\"“”'‘’:;,!?…>]", " ", text)
        return _clean(base(text))

    return tokenize
