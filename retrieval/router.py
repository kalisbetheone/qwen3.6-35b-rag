"""Direct lookup: bắt tham chiếu tường minh ("Điều 7 Nghị định 125", "khoản 2 điều 9 NĐ 125/2026")
và lấy thẳng theo metadata, bỏ qua tìm kiếm."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from common.schema import DocMeta

LOAI_TU_KHOA = {
    "bộ luật": "Bộ luật", "luật": "Luật", "nghị quyết": "Nghị quyết", "nq": "Nghị quyết",
    "nghị định": "Nghị định", "nđ": "Nghị định", "nd": "Nghị định",
    "thông tư liên tịch": "Thông tư liên tịch", "ttlt": "Thông tư liên tịch",
    "thông tư": "Thông tư", "tt": "Thông tư", "quyết định": "Quyết định", "qđ": "Quyết định",
    "quy chế": "Quy chế", "qc": "Quy chế",
}
_LOAI_ALT = "|".join(sorted(map(re.escape, LOAI_TU_KHOA), key=len, reverse=True))

RE_ART_REF = re.compile(
    r"(?:điểm\s+(?P<diem>[a-zđ])\s*,?\s*)?"
    r"(?:khoản\s+(?P<khoan>\d+(?:\s*(?:,|và|&)\s*\d+)*)\s*,?\s*(?:của\s+)?)?"
    r"điều\s+(?P<dieu>\d+[a-z]?)\b",
    re.I,
)
RE_DOC_REF = re.compile(
    rf"\b(?P<loai>{_LOAI_ALT})\s*(?:số\s*)?(?P<num>\d+)(?:\s*/\s*(?P<year>\d{{4}}))?", re.I
)
RE_SO_HIEU = re.compile(r"\b(?P<num>\d+)\s*/\s*(?P<year>\d{4})\s*/\s*[A-ZĐ][A-ZĐ0-9\-]*", re.I)


@dataclass
class RouteHit:
    doc_id: str
    dieu: str
    khoan: list[int] | None = None
    diem: str | None = None

    @property
    def article_id(self) -> str:
        return f"{self.doc_id}_d{self.dieu}"


@dataclass
class _DocRef:
    start: int
    end: int
    doc_ids: list[str]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower()


class Router:
    def __init__(self, docs: Iterable[DocMeta], default_doc_id: str | None = None):
        self.docs = list(docs)
        self.default_doc_id = default_doc_id

    def _match_docs(self, loai: str | None, num: str, year: str | None) -> list[str]:
        out = []
        for d in self.docs:
            parts = d.so_hieu.split("/")
            if parts[0] != num:
                continue
            if year and (len(parts) < 2 or parts[1] != year):
                continue
            if loai and d.loai != loai:
                continue
            out.append(d)
        out.sort(key=lambda d: d.hieu_luc != "con_hieu_luc")  # ưu tiên văn bản còn hiệu lực
        return [d.doc_id for d in out]

    def _doc_refs(self, q: str) -> list[_DocRef]:
        refs: list[_DocRef] = []
        for m in RE_DOC_REF.finditer(q):
            loai = LOAI_TU_KHOA[_norm(m.group("loai"))]
            ids = self._match_docs(loai, m.group("num"), m.group("year"))
            if ids:
                refs.append(_DocRef(m.start(), m.end(), ids))
        for m in RE_SO_HIEU.finditer(q):
            if any(r.start <= m.start() < r.end for r in refs):
                continue
            ids = self._match_docs(None, m.group("num"), m.group("year"))
            if ids:
                refs.append(_DocRef(m.start(), m.end(), ids))
        nq = _norm(q)
        for d in self.docs:
            for alias in d.aliases:
                pos = nq.find(_norm(alias))
                if pos >= 0 and not any(r.start <= pos < r.end for r in refs):
                    refs.append(_DocRef(pos, pos + len(alias), [d.doc_id]))
        return sorted(refs, key=lambda r: r.start)

    def route(self, question: str, doc_filter: list[str] | None = None) -> list[RouteHit]:
        q = unicodedata.normalize("NFC", question)
        arts = list(RE_ART_REF.finditer(q))
        if not arts:
            return []
        refs = self._doc_refs(q)
        hits: list[RouteHit] = []
        for m in arts:
            after = [r for r in refs if r.start >= m.end()]
            before = [r for r in refs if r.end <= m.start()]
            if after:
                doc_ids = after[0].doc_ids
            elif before:
                doc_ids = before[-1].doc_ids
            elif doc_filter and len(doc_filter) == 1:
                doc_ids = list(doc_filter)
            elif self.default_doc_id:
                doc_ids = [self.default_doc_id]
            else:
                continue  # không rõ văn bản -> để tìm kiếm thường xử lý
            khoan = [int(x) for x in re.findall(r"\d+", m.group("khoan"))] if m.group("khoan") else None
            diem = m.group("diem").lower() if m.group("diem") else None
            hit = RouteHit(doc_ids[0], m.group("dieu").lower(), khoan, diem)
            if hit not in hits:
                hits.append(hit)
        return hits
