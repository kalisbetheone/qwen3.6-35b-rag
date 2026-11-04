import pytest

from common.config import ChunkingCfg, load_config
from common.schema import DocMeta
from ingest.chunker import Chunker
from ingest.parser import parse_file
from retrieval.bm25 import BM25Index
from retrieval.pipeline import RetrievalPipeline
from retrieval.router import Router
from retrieval.store import ChunkStore

from .conftest import FIXTURES, ROOT

INTERNAL = DocMeta(doc_id="qc-mau-noibo-01", so_hieu="01/QC-MẪU", loai="Quy chế", ten="Quy chế mẫu",
                   access_level="internal", alias="Quy chế mẫu")
OLD = DocMeta(doc_id="nd999-2098", so_hieu="999/2098/NĐ-CP", loai="Nghị định", hieu_luc="het_hieu_luc",
              thay_the_boi="999/2099/NĐ-CP")


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    meta = DocMeta(doc_id="nd999-2099", so_hieu="999/2099/NĐ-CP", loai="Nghị định", alias="Nghị định mẫu")
    chunker = Chunker(ChunkingCfg(min_article_tokens=60, max_clause_tokens=700))
    c1, a1 = chunker.chunk_document(meta, parse_file(FIXTURES / "nd_mau_kiem_thu.txt"))
    c2, a2 = chunker.chunk_document(INTERNAL, parse_file(ROOT / "data" / "raw" / "qc-mau-noibo-01.txt"))
    store = ChunkStore(c1 + c2, a1 + a2, [meta, INTERNAL, OLD])
    out = tmp_path_factory.mktemp("idx")
    store.save(out)
    BM25Index("underthesea").build([c.text_for_embed for c in store.chunks]).save(out / "bm25")
    cfg = load_config(overrides={"retrieval.use_dense": False, "retrieval.use_rerank": False})
    return RetrievalPipeline.load(cfg, out)


# ------------------------------------------------------------ router


@pytest.fixture
def router():
    docs = [DocMeta(doc_id="nd125-2026", so_hieu="125/2026/NĐ-CP", loai="Nghị định", alias="NĐ 125"),
            DocMeta(doc_id="luat125-2025", so_hieu="125/2025/QH15", loai="Luật", alias="Luật Giáo dục đại học"),
            DocMeta(doc_id="nd109-2022", so_hieu="109/2022/NĐ-CP", loai="Nghị định", hieu_luc="het_hieu_luc")]
    return Router(docs)


@pytest.mark.parametrize("q,expected", [
    ("Điều 7 Nghị định 125 quy định gì?", [("nd125-2026", "7", None, None)]),
    ("khoản 2 điều 9 NĐ 125/2026/NĐ-CP", [("nd125-2026", "9", [2], None)]),
    ("Theo Nghị định số 109/2022, Điều 3 nói gì", [("nd109-2022", "3", None, None)]),
    ("điểm a khoản 1 Điều 12 Luật Giáo dục đại học", [("luat125-2025", "12", [1], "a")]),
    ("So sánh Điều 7 và Điều 9 của 125/2026/NĐ-CP", [("nd125-2026", "7", None, None), ("nd125-2026", "9", None, None)]),
    ("khoản 2, 3 Điều 5 Luật 125/2025", [("luat125-2025", "5", [2, 3], None)]),
])
def test_router_patterns(router, q, expected):
    hits = router.route(q)
    assert [(h.doc_id, h.dieu, h.khoan, h.diem) for h in hits] == expected


def test_router_no_doc_falls_back(router):
    assert router.route("khoản 2 điều 9 quy định gì") == []
    assert router.route("khoản 2 điều 9 quy định gì", doc_filter=["nd125-2026"])[0].doc_id == "nd125-2026"
    assert router.route("Giảng viên được giảm giờ chuẩn không?") == []


# ------------------------------------------------------------ pipeline (BM25-only)


def test_direct_lookup_article_and_clause(pipeline):
    r = pipeline.retrieve("Điều 4 Nghị định 999/2099 quy định gì?", ["public"])
    assert r.route == "direct" and r.sources[0].parent_article_id == "nd999-2099_d4"
    assert r.sources[0].text.startswith("Điều 4.")
    r = pipeline.retrieve("khoản 2 Điều 7 NĐ 999/2099", ["public"])
    assert r.route == "direct"
    assert r.sources[0].chunk_ids == ["nd999-2099_d7_k2"] or r.sources[0].parent_article_id == "nd999-2099_d7"


def test_missing_reference_reported(pipeline):
    r = pipeline.retrieve("Điều 99 Nghị định 999/2099 quy định gì?", ["public"])
    assert r.route == "search" and r.missing_refs == ["Điều 99 NĐ 999/2099/NĐ-CP"]


@pytest.mark.parametrize("q,article", [
    ("Trưởng nhóm nghiên cứu được giảm bao nhiêu định mức giờ chuẩn?", "nd999-2099_d6"),
    ("Thời gian nghiên cứu tối thiểu của giảng viên là bao nhiêu?", "nd999-2099_d4"),
    ("Nghị định này có hiệu lực từ ngày nào?", "nd999-2099_d7"),
    ("Đề tài mẫu được hiểu là gì?", "nd999-2099_d3"),
    ("Người học có thuộc đối tượng áp dụng không?", "nd999-2099_d2"),
])
def test_bm25_reasonable(pipeline, q, article):
    r = pipeline.retrieve(q, ["public"])
    assert not r.no_evidence
    assert article in [s.parent_article_id for s in r.sources[:3]]


def test_access_control(pipeline):
    q = "Thời gian thực hiện đề tài cấp cơ sở tối đa bao lâu, có được gia hạn không?"
    student = pipeline.retrieve(q, ["public"])
    assert all(s.access_level == "public" for s in student.sources)
    staff = pipeline.retrieve(q, ["public", "internal"])
    assert staff.sources[0].doc_id == "qc-mau-noibo-01"
    # học viên không lấy được Điều nội bộ kể cả khi tham chiếu trực tiếp
    r = pipeline.retrieve("Điều 5 Quy chế mẫu", ["public"])
    assert all(s.doc_id != "qc-mau-noibo-01" for s in r.sources)


def test_doc_filter(pipeline):
    r = pipeline.retrieve("đề tài", ["public", "internal"], doc_filter=["nd999-2099"])
    assert {s.doc_id for s in r.sources} <= {"nd999-2099"}


def test_parent_expansion(pipeline):
    store = pipeline.store
    srcs = [store.chunk_source(store.pos["nd999-2099_d7"], 0.9, "x")]
    # 2 Khoản cùng Điều 4 -> gộp thành nguyên Điều 4
    a = store.chunk_source(store.pos["nd999-2099_d4_k2"], 0.8, "x")
    b = store.chunk_source(store.pos["nd999-2099_d4_k1"], 0.7, "x")
    out = pipeline._expand_parents(srcs + [a, b])
    assert [s.parent_article_id for s in out] == ["nd999-2099_d7", "nd999-2099_d4"]
    assert out[1].score == 0.8 and out[1].extra["expanded_from"] == 2
    assert out[1].text.startswith("Điều 4.") and out[1].chunk_ids == ["nd999-2099_d4_k2", "nd999-2099_d4_k1"]


def test_status_note(pipeline):
    assert pipeline.store.status_note("nd999-2098") == "hết hiệu lực, được thay thế bởi 999/2099/NĐ-CP"
