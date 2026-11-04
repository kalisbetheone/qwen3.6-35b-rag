"""Chunk theo cấu trúc pháp lý: mặc định 1 Khoản; Điều ngắn -> cả Điều; Khoản dài -> tách theo điểm."""
from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache

from common.config import ChunkingCfg
from common.schema import ArticleRec, Chunk, ClauseRec, DocMeta, PointRec
from ingest.parser import Article, Clause, ParsedDocument, Point, render_article, render_clause


def heuristic_tokens(text: str) -> int:
    # ~1,35 token / âm tiết tiếng Việt với tokenizer BPE đa ngôn ngữ (đủ để quyết định cắt)
    return max(1, math.ceil(len(text.split()) * 1.35))


@lru_cache(maxsize=4)
def _hf_counter(name: str) -> Callable[[str], int]:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(name)
    return lambda t: len(tok.encode(t, add_special_tokens=False))


def get_token_counter(name: str) -> Callable[[str], int]:
    if name == "heuristic":
        return heuristic_tokens
    try:
        return _hf_counter(name)
    except Exception:  # không có transformers / không tải được -> ước lượng
        return heuristic_tokens


def _sentence_case(title: str | None) -> str | None:
    if title and title.isupper():
        return title[0] + title[1:].lower()
    return title


def _letter_id(letter: str) -> str:
    return letter.replace("đ", "dd")


def article_header(meta: DocMeta, a: Article, khoan: int | None = None, diem: str | None = None,
                   unit: str = "Điều") -> str:
    parts = [meta.label]
    if a.chapter:
        ct = _sentence_case(a.chapter_title)
        parts.append(f"Chương {a.chapter}: {ct}" if ct else f"Chương {a.chapter}")
    parts.append(f"{unit} {a.number}: {a.title}" if a.title else f"{unit} {a.number}")
    if khoan is not None:
        parts.append(f"Khoản {khoan}")
    if diem:
        parts.append(f"Điểm {diem}")
    return "[" + " > ".join(parts) + "]"


def citation_label(meta: DocMeta, dieu: str, khoan: int | None = None, diem: str | None = None,
                   unit: str = "Điều") -> str:
    s = f"{unit} {dieu}"
    if khoan is not None:
        s = f"Khoản {khoan} {s}"
    if diem:
        s = f"Điểm {diem} {s}"
    return f"{s}, {meta.label}"


def _group_points(lead: str, points: list[Point], max_tokens: int, count) -> list[list[Point]]:
    groups: list[list[Point]] = [[]]
    for p in points:
        trial = "\n".join([lead, *(f"{q.letter}) {q.text}" for q in groups[-1] + [p])])
        if groups[-1] and count(trial) > max_tokens:
            groups.append([])
        groups[-1].append(p)
    return groups


class Chunker:
    def __init__(self, cfg: ChunkingCfg):
        self.cfg = cfg
        self.count = get_token_counter(cfg.tokenizer)
        self.unit = "Điều"  # đặt theo văn bản đang xử lý ("Phần" với tài liệu không có cấu trúc Điều)

    def _make(self, meta: DocMeta, a: Article, display: str, khoan=None, diem=None, diem_id=None) -> Chunk:
        art_id = f"{meta.doc_id}_d{a.number}"
        cid = art_id + (f"_k{khoan}" if khoan is not None else "") + (f"_{diem_id}" if diem_id else "")
        header = article_header(meta, a, khoan, diem, self.unit)
        intro = ""
        if (khoan is not None or diem) and a.intro and self.count(a.intro) <= self.cfg.max_intro_tokens:
            intro = a.intro + "\n"
        return Chunk(
            chunk_id=cid, doc_id=meta.doc_id, so_hieu=meta.so_hieu, loai=meta.loai, ten_van_ban=meta.ten,
            chuong=a.chapter, ten_chuong=_sentence_case(a.chapter_title), muc=a.section, ten_muc=a.section_title,
            dieu=a.number, ten_dieu=a.title or None, khoan=khoan, diem=diem,
            citation_label=citation_label(meta, a.number, khoan, diem, self.unit),
            text_for_embed=f"{header}\n{intro}{display}", text_display=display,
            n_tokens=self.count(display), hieu_luc=meta.hieu_luc, access_level=meta.access_level,
            url_nguon=meta.url_nguon, parent_article_id=art_id,
        )

    def _split_points(self, meta: DocMeta, a: Article, c: Clause) -> list[Chunk]:
        lead = render_clause(c, points=[])
        out = []
        for g in _group_points(lead, c.points, self.cfg.max_clause_tokens, self.count):
            first, last = g[0].letter, g[-1].letter
            diem = first if first == last else f"{first}–{last}"
            diem_id = _letter_id(first) if first == last else f"{_letter_id(first)}-{_letter_id(last)}"
            out.append(self._make(meta, a, render_clause(c, points=g), c.number, diem, diem_id))
        return out

    def chunk_article(self, meta: DocMeta, a: Article) -> list[Chunk]:
        full = render_article(a, self.unit)
        if not a.real_clauses:
            if self.count(full) > self.cfg.max_clause_tokens and a.clauses and a.clauses[0].points:
                # Điều chỉ có điểm, quá dài: câu dẫn của Điều làm lead
                c = Clause(number=None, text=a.intro, points=[p for cl in a.clauses for p in cl.points])
                saved, a.intro = a.intro, ""
                try:
                    return self._split_points(meta, a, c)
                finally:
                    a.intro = saved
            return [self._make(meta, a, full)]
        if self.count(full) < self.cfg.min_article_tokens:
            return [self._make(meta, a, full)]
        out: list[Chunk] = []
        for c in a.clauses:
            if c.number is None:  # điểm lạc trước Khoản 1: bỏ qua ở mức chunk (vẫn có trong nguyên văn Điều)
                continue
            text = render_clause(c)
            if self.count(text) > self.cfg.max_clause_tokens and c.points:
                out.extend(self._split_points(meta, a, c))
            else:
                out.append(self._make(meta, a, text, c.number))
        return out

    def article_record(self, meta: DocMeta, a: Article) -> ArticleRec:
        return ArticleRec(
            article_id=f"{meta.doc_id}_d{a.number}", doc_id=meta.doc_id, so_hieu=meta.so_hieu, loai=meta.loai,
            ten_van_ban=meta.ten, chuong=a.chapter, ten_chuong=_sentence_case(a.chapter_title), dieu=a.number,
            ten_dieu=a.title or None, intro=a.intro,
            clauses=[ClauseRec(khoan=c.number, text=c.text, points=[PointRec(diem=p.letter, text=p.text) for p in c.points])
                     for c in a.clauses],
            text=render_article(a, self.unit), citation_label=citation_label(meta, a.number, unit=self.unit),
            header=article_header(meta, a, unit=self.unit), hieu_luc=meta.hieu_luc, access_level=meta.access_level,
            url_nguon=meta.url_nguon,
        )

    def chunk_document(self, meta: DocMeta, doc: ParsedDocument) -> tuple[list[Chunk], list[ArticleRec]]:
        self.unit = doc.unit
        chunks, arts = [], []
        for a in doc.articles:
            chunks.extend(self.chunk_article(meta, a))
            arts.append(self.article_record(meta, a))
        return chunks, arts
