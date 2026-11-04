"""Hậu kiểm trích dẫn: gỡ nhãn [n] sai phạm vi, đánh dấu câu weak / unsupported, tính grounding_score."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

# Nhóm nhãn mở đầu bằng số nguồn; các phần sau có thể lẫn chỉ dẫn vị trí do LLM tự thêm,
# vd [1, 3a], [2, 2đ], [1, Khoản 2] — chỉ phần là số nguyên mới được coi là số nguồn.
RE_CITE_GROUP = re.compile(r"\s*\[(\d+(?:\s*[,;]\s*[^\[\]\n,;]{1,40})*)\]")
RE_SOURCE_NUM = re.compile(r"^\s*(\d+)\s*$")
RE_BOUNDARY = re.compile(r"[.!?…](?:\s*\[\d+(?:\s*[,;]\s*[^\[\]\n,;]{1,40})*\])*(?=\s|$)")
RE_LIST_MARK = re.compile(r"^\s*(?:[-*+•]|\d+[.)]|[a-zđ]\))\s+")
RE_NUMERIC = re.compile(r"\d|%|phần trăm", re.I)
REFUSAL_PHRASES = ("không quy định", "không tìm thấy", "không có quy định", "chưa có quy định", "không đủ căn cứ")

Scorer = Callable[[list[tuple[str, str]]], list[float]]


@dataclass
class Sentence:
    text: str
    start: int
    end: int
    cites: list[int]
    flag: str | None = None  # weak | unsupported
    support: float | None = None


@dataclass
class VerifyResult:
    answer: str
    sentences: list[Sentence]
    citations_used: list[int]
    grounding_score: float | None
    flags: list[dict] = field(default_factory=list)
    invalid_citations: list[int] = field(default_factory=list)
    is_refusal: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _group_nums(group: str) -> list[int]:
    return [int(m.group(1)) for part in re.split(r"[,;]", group) if (m := RE_SOURCE_NUM.match(part))]


def parse_cites(s: str) -> list[int]:
    return [n for g in RE_CITE_GROUP.findall(s) for n in _group_nums(g)]


def strip_cites(s: str) -> str:
    return RE_CITE_GROUP.sub("", s).strip()


def clean_invalid(answer: str, n_sources: int) -> tuple[str, list[int]]:
    invalid: list[int] = []

    def fix(m: re.Match) -> str:
        nums = _group_nums(m.group(1))  # "3a", "Khoản 2"… bị bỏ khi viết lại nhãn
        ok = [n for n in nums if 1 <= n <= n_sources]
        invalid.extend(n for n in nums if n not in ok)
        lead = m.group(0)[: len(m.group(0)) - len(m.group(0).lstrip())]
        return f"{lead}[{', '.join(map(str, dict.fromkeys(ok)))}]" if ok else ""

    return RE_CITE_GROUP.sub(fix, answer), invalid


def split_sentences(text: str) -> list[Sentence]:
    out: list[Sentence] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        lm = RE_LIST_MARK.match(body)
        start = lm.end() if lm else len(body) - len(body.lstrip())
        if body.lstrip().startswith("#"):
            offset += len(line)
            continue
        pos = start
        for m in RE_BOUNDARY.finditer(body, start):
            seg = body[pos:m.end()]
            if strip_cites(seg).strip(" .!?…"):
                lead = len(seg) - len(seg.lstrip())
                out.append(Sentence(seg.strip(), offset + pos + lead, offset + m.end(), parse_cites(seg)))
            pos = m.end()
        seg = body[pos:]
        if strip_cites(seg).strip(" .!?…"):
            lead = len(seg) - len(seg.lstrip())
            out.append(Sentence(seg.strip(), offset + pos + lead, offset + pos + len(seg.rstrip()), parse_cites(seg)))
        offset += len(line)
    return out


def _is_refusal(s: str) -> bool:
    low = s.lower()
    return any(p in low for p in REFUSAL_PHRASES)


def _is_claim(s: Sentence) -> bool:
    plain = strip_cites(s.text)
    if s.cites:
        return True
    if plain.endswith(":"):
        return False  # câu dẫn liệt kê, vd "Theo Điều 6 NĐ 125/2026/NĐ-CP:" — nội dung nằm ở các ý bên dưới
    return len(plain.split()) >= 4


# Số hiệu, số Điều/Khoản/Điểm/Chương không phải "số liệu" cần dẫn nguồn
RE_LEGAL_REF = re.compile(
    r"\b(?:điều|khoản|điểm|chương|mục)\s+\d+[a-z]?\b"
    r"|\b\d+(?:/\d{2,4})+(?:/[A-ZĐ][A-ZĐ0-9\-]*)?"
    r"|\b(?:nghị định|nđ|luật|thông tư|tt|quyết định|qđ|nghị quyết|nq)\s+(?:số\s+)?\d+(?:/\d{2,4})*(?:/[A-ZĐ][A-ZĐ0-9\-]*)?",
    re.I,
)


def _has_figures(plain: str) -> bool:
    """Câu có con số/tỷ lệ/thời hạn thật (sau khi bỏ số hiệu văn bản và số Điều/Khoản)."""
    return bool(RE_NUMERIC.search(RE_LEGAL_REF.sub(" ", plain)))


def verify(answer: str, source_texts: list[str], scorer: Scorer | None = None,
           weak_threshold: float = 0.2) -> VerifyResult:
    cleaned, invalid = clean_invalid(answer, len(source_texts))
    sents = split_sentences(cleaned)

    # weak: câu có nhãn nhưng không giống chunk được trích (dùng lại reranker)
    if scorer is not None:
        pairs, owners = [], []
        for i, s in enumerate(sents):
            for n in dict.fromkeys(s.cites):
                pairs.append((strip_cites(s.text), source_texts[n - 1]))
                owners.append(i)
        if pairs:
            best: dict[int, float] = {}
            for i, sc in zip(owners, scorer(pairs), strict=True):
                best[i] = max(best.get(i, 0.0), float(sc))
            for i, sc in best.items():
                sents[i].support = sc
                if sc < weak_threshold:
                    sents[i].flag = "weak"

    refusal_only = True
    claims = grounded = 0
    for s in sents:
        if _is_refusal(s.text) and not s.cites:
            continue
        refusal_only = False
        if not _is_claim(s):
            continue
        claims += 1
        if s.cites and s.flag is None:
            grounded += 1
        elif not s.cites and _has_figures(strip_cites(s.text)):
            s.flag = "unsupported"

    flags = [{"sentence_idx": i, "type": s.flag, "sentence": s.text} for i, s in enumerate(sents) if s.flag]
    used = sorted({n for s in sents for n in s.cites})
    return VerifyResult(
        answer=cleaned, sentences=sents, citations_used=used,
        grounding_score=(grounded / claims) if claims else None, flags=flags,
        invalid_citations=sorted(set(invalid)), is_refusal=bool(sents) and refusal_only,
    )
