"""Schema dữ liệu dùng chung: văn bản (registry), chunk, Điều."""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AccessLevel = Literal["public", "internal"]
HieuLuc = Literal["con_hieu_luc", "het_hieu_luc"]

LOAI_VIET_TAT = {
    "Luật": "Luật",
    "Bộ luật": "BL",
    "Nghị quyết": "NQ",
    "Nghị định": "NĐ",
    "Quyết định": "QĐ",
    "Thông tư": "TT",
    "Thông tư liên tịch": "TTLT",
    "Quy chế": "QC",
    "Quy định": "QĐ",
}


class DocMeta(BaseModel):
    """Một dòng của data/registry.csv."""

    doc_id: str
    so_hieu: str
    loai: str
    ten: str = ""
    ngay_ban_hanh: str = ""
    hieu_luc: HieuLuc = "con_hieu_luc"
    co_quan: str = ""
    url_nguon: str = ""
    access_level: AccessLevel = "public"
    so_dieu: int | None = None  # đếm tay, dùng để kiểm parser
    file: str = ""  # tên file trong data/raw (bỏ trống -> đoán theo doc_id/so_hieu)
    thay_the_boi: str = ""  # số hiệu văn bản thay thế (nếu hết hiệu lực)
    alias: str = ""  # tên gọi khác, cách nhau bằng ';' (cho router)
    ghi_chu: str = ""
    source: Literal["registry", "upload"] = "registry"  # upload = do giảng viên thêm qua giao diện
    uploaded_by: str = ""

    @field_validator("so_dieu", mode="before")
    @classmethod
    def _empty_int(cls, v):
        if v is None or (isinstance(v, float) and v != v) or str(v).strip() == "":
            return None
        return int(float(v))

    @property
    def label(self) -> str:
        """Nhãn ngắn: 'NĐ 125/2026/NĐ-CP', 'Luật 93/2025/QH15'; tài liệu không có số hiệu dùng tên."""
        if not self.so_hieu:
            return self.ten[:80] or self.doc_id
        return f"{LOAI_VIET_TAT.get(self.loai, self.loai)} {self.so_hieu}"

    @property
    def aliases(self) -> list[str]:
        return [a.strip() for a in self.alias.split(";") if a.strip()]


class Chunk(BaseModel):
    chunk_id: str = Field(pattern=r"^[a-z0-9-]+_d[0-9a-z]+(_k\d+)?(_[a-z]+(-[a-z]+)?)?$")
    doc_id: str
    so_hieu: str
    loai: str
    ten_van_ban: str = ""
    chuong: str | None = None
    ten_chuong: str | None = None
    muc: str | None = None
    ten_muc: str | None = None
    dieu: str
    ten_dieu: str | None = None
    khoan: int | None = None
    diem: str | None = None
    citation_label: str
    text_for_embed: str
    text_display: str
    n_tokens: int
    hieu_luc: HieuLuc = "con_hieu_luc"
    access_level: AccessLevel = "public"
    url_nguon: str = ""
    parent_article_id: str


class PointRec(BaseModel):
    diem: str
    text: str


class ClauseRec(BaseModel):
    khoan: int | None = None  # None = các điểm nằm thẳng dưới Điều
    text: str = ""
    points: list[PointRec] = Field(default_factory=list)


class ArticleRec(BaseModel):
    """Nguyên văn một Điều (data/processed/articles.jsonl) — cho khung nguồn và parent expansion."""

    article_id: str
    doc_id: str
    so_hieu: str
    loai: str
    ten_van_ban: str = ""
    chuong: str | None = None
    ten_chuong: str | None = None
    dieu: str
    ten_dieu: str | None = None
    intro: str = ""
    clauses: list[ClauseRec] = Field(default_factory=list)
    text: str
    citation_label: str
    header: str
    hieu_luc: HieuLuc = "con_hieu_luc"
    access_level: AccessLevel = "public"
    url_nguon: str = ""


def write_jsonl(path: Path, rows: Iterable[BaseModel | dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            d = r.model_dump() if isinstance(r, BaseModel) else r
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_registry(path: Path, source: str = "registry") -> list[DocMeta]:
    import csv

    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(f)]
    return [DocMeta.model_validate({**r, "source": source}) for r in rows]


def save_registry(path: Path, docs: list[DocMeta]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [f for f in DocMeta.model_fields if f != "source"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in docs:
            row = d.model_dump(exclude={"source"})
            w.writerow({k: "" if row[k] is None else row[k] for k in fields})
