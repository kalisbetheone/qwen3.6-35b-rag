"""Kho chunk + Điều + danh mục văn bản trong một index; lọc metadata (phân quyền, phạm vi văn bản)."""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from common.schema import ArticleRec, Chunk, DocMeta, read_jsonl


@dataclass
class Source:
    """Một nguồn đưa cho LLM / hiển thị ở khung phải (1 chunk hoặc nguyên Điều sau parent expansion)."""

    chunk_ids: list[str]
    doc_id: str
    so_hieu: str
    dieu: str
    khoan: int | None
    diem: str | None
    citation_label: str
    header: str
    text: str
    score: float
    url_nguon: str = ""
    hieu_luc: str = "con_hieu_luc"
    access_level: str = "public"
    parent_article_id: str = ""
    retriever: str = "hybrid"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ChunkStore:
    def __init__(self, chunks: list[Chunk], articles: list[ArticleRec], docs: list[DocMeta]):
        self.chunks = chunks
        self.ids = [c.chunk_id for c in chunks]
        self.pos = {cid: i for i, cid in enumerate(self.ids)}
        self.articles = {a.article_id: a for a in articles}
        self.docs = {d.doc_id: d for d in docs}
        self._level = np.array([c.access_level for c in chunks])
        self._doc = np.array([c.doc_id for c in chunks])
        self.by_article: dict[str, list[int]] = {}
        for i, c in enumerate(chunks):
            self.by_article.setdefault(c.parent_article_id, []).append(i)

    # ------------------------------------------------------------ I/O
    @classmethod
    def from_files(cls, chunks_path: Path, articles_path: Path, docs: list[DocMeta]) -> ChunkStore:
        chunks = [Chunk.model_validate(d) for d in read_jsonl(chunks_path)]
        arts = [ArticleRec.model_validate(d) for d in read_jsonl(articles_path)] if articles_path.exists() else []
        return cls(chunks, arts, docs)

    def save(self, index_dir: Path) -> None:
        import pandas as pd

        index_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([c.model_dump() for c in self.chunks]).to_parquet(index_dir / "meta.parquet", index=False)
        with (index_dir / "articles.jsonl").open("w", encoding="utf-8") as f:
            for a in self.articles.values():
                f.write(a.model_dump_json() + "\n")
        (index_dir / "docs.json").write_text(
            json.dumps([d.model_dump() for d in self.docs.values()], ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, index_dir: Path) -> ChunkStore:
        import pandas as pd

        df = pd.read_parquet(index_dir / "meta.parquet")
        rows = df.astype(object).where(df.notna(), None).to_dict("records")
        chunks = [Chunk.model_validate(r) for r in rows]
        arts = [ArticleRec.model_validate(d) for d in read_jsonl(index_dir / "articles.jsonl")]
        docs = [DocMeta.model_validate(d) for d in json.loads((index_dir / "docs.json").read_text(encoding="utf-8"))]
        return cls(chunks, arts, docs)

    # ------------------------------------------------------------ lọc
    def mask(self, allowed_levels: Iterable[str], doc_filter: Iterable[str] | None = None) -> np.ndarray:
        m = np.isin(self._level, list(allowed_levels))
        if doc_filter:
            m &= np.isin(self._doc, list(doc_filter))
        return m

    def visible_docs(self, allowed_levels: Iterable[str]) -> list[DocMeta]:
        lv = set(allowed_levels)
        return [d for d in self.docs.values() if d.access_level in lv]

    # ------------------------------------------------------------ dựng Source
    def doc_label(self, doc_id: str) -> str:
        d = self.docs.get(doc_id)
        return d.label if d else doc_id

    def status_note(self, doc_id: str) -> str:
        d = self.docs.get(doc_id)
        if d and d.hieu_luc == "het_hieu_luc":
            return "hết hiệu lực" + (f", được thay thế bởi {d.thay_the_boi}" if d.thay_the_boi else "")
        return ""

    def chunk_source(self, i: int, score: float, retriever: str) -> Source:
        c = self.chunks[i]
        header = c.text_for_embed.split("\n", 1)[0]
        return Source(
            chunk_ids=[c.chunk_id], doc_id=c.doc_id, so_hieu=c.so_hieu, dieu=c.dieu, khoan=c.khoan, diem=c.diem,
            citation_label=c.citation_label, header=header, text=c.text_display, score=float(score),
            url_nguon=c.url_nguon, hieu_luc=c.hieu_luc, access_level=c.access_level,
            parent_article_id=c.parent_article_id, retriever=retriever,
        )

    def article_source(self, article_id: str, score: float, retriever: str, chunk_ids: list[str] | None = None) -> Source | None:
        a = self.articles.get(article_id)
        if a is None:
            return None
        ids = chunk_ids or [self.ids[i] for i in self.by_article.get(article_id, [])]
        return Source(
            chunk_ids=ids, doc_id=a.doc_id, so_hieu=a.so_hieu, dieu=a.dieu, khoan=None, diem=None,
            citation_label=a.citation_label, header=a.header, text=a.text, score=float(score),
            url_nguon=a.url_nguon, hieu_luc=a.hieu_luc, access_level=a.access_level,
            parent_article_id=article_id, retriever=retriever,
        )
