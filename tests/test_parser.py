from pathlib import Path

import pytest

from common.config import ChunkingCfg, load_config
from common.schema import DocMeta, load_registry
from ingest.chunker import Chunker
from ingest.parser import parse_file, parse_lines
from ingest.run_ingest import find_raw_file


def test_article_count_and_structure(sample_doc):
    arts = sample_doc.articles
    assert [a.number for a in arts] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [c.number for c in sample_doc.chapters] == ["I", "II", "III"]
    assert sample_doc.chapters[0].title == "QUY ĐỊNH CHUNG"
    a4 = arts[3]
    assert a4.title == "Nhiệm vụ của giảng viên mẫu"
    assert a4.section == "1" and a4.section_title == "NHIỆM VỤ VÀ QUYỀN"
    assert [p.letter for p in a4.clauses[0].points] == ["a", "b", "c", "d", "đ"]
    assert arts[5].section == "2"


def test_preamble_and_tail_excluded(sample_doc):
    assert any(line.startswith("Căn cứ") for line in sample_doc.preamble)
    assert sample_doc.tail[0].startswith("Nơi nhận")
    assert "Như trên" not in sample_doc.articles[-1].clauses[-1].text


def test_broken_line_merged(sample_doc):
    a2 = sample_doc.articles[1]
    assert a2.clauses[1].text == "Người học tham gia hoạt động nghiên cứu khoa học tại cơ sở giáo dục mẫu."


def test_quoted_amendment_not_parsed_as_article(sample_doc):
    a5 = sample_doc.articles[4]
    assert len(a5.real_clauses) == 2
    assert "“Điều 9." in a5.clauses[0].text


def test_intro_and_article_without_clauses(sample_doc):
    a3 = sample_doc.articles[2]
    assert a3.intro.startswith("Trong Nghị định này")
    a6 = sample_doc.articles[5]
    assert not a6.clauses and "50%" in a6.intro


def test_point_directly_under_article():
    doc = parse_lines(["Điều 1. Tên", "Các trường hợp sau:", "a) Thứ nhất;", "b) Thứ hai."])
    a = doc.articles[0]
    assert a.clauses[0].number is None and len(a.clauses[0].points) == 2


def test_pdf_aggressive_merge_keeps_article_title():
    doc = parse_lines(["Điều 1. Phạm vi điều chỉnh", "Nghị định này quy định về việc", "Mẫu và các nội dung khác."],
                      aggressive=True)
    a = doc.articles[0]
    assert a.title == "Phạm vi điều chỉnh"
    assert a.intro == "Nghị định này quy định về việc Mẫu và các nội dung khác."


# ------------------------------------------------------------ chunker


def test_short_articles_kept_whole(sample_chunks):
    chunks, arts = sample_chunks
    ids = [c.chunk_id for c in chunks]
    assert "nd999-2099_d4" in ids  # Điều 4 ngắn hơn 300 token -> nguyên Điều
    assert len(arts) == 7 and len(ids) == len(set(ids))


def test_header_and_citation(sample_chunks):
    chunks, _ = sample_chunks
    c = next(c for c in chunks if c.chunk_id == "nd999-2099_d4")
    assert c.text_for_embed.startswith("[NĐ 999/2099/NĐ-CP > Chương II: Hoạt động nghiên cứu mẫu > Điều 4: Nhiệm vụ")
    assert c.citation_label == "Điều 4, NĐ 999/2099/NĐ-CP"
    assert c.text_display.startswith("Điều 4. Nhiệm vụ")


def test_clause_and_point_split(sample_meta, sample_doc):
    cfg = ChunkingCfg(min_article_tokens=10, max_clause_tokens=40)
    chunks, _ = Chunker(cfg).chunk_document(sample_meta, sample_doc)
    by_id = {c.chunk_id: c for c in chunks}
    assert "nd999-2099_d2_k2" in by_id
    assert by_id["nd999-2099_d2_k2"].citation_label == "Khoản 2 Điều 2, NĐ 999/2099/NĐ-CP"
    point_chunks = [c for c in chunks if c.chunk_id.startswith("nd999-2099_d4_k1_")]
    assert len(point_chunks) >= 2
    for c in point_chunks:  # mỗi phần giữ câu dẫn của Khoản
        assert c.text_display.startswith("1. Giảng viên có các nhiệm vụ sau đây:")
    assert point_chunks[-1].chunk_id.endswith("dd") or "-dd" in point_chunks[-1].chunk_id
    # câu dẫn của Điều 3 được ghép vào text_for_embed của Khoản
    assert "Trong Nghị định này" in by_id["nd999-2099_d3_k1"].text_for_embed
    assert all(c.parent_article_id == "nd999-2099_" + c.chunk_id.split("_")[1] for c in chunks)


# ------------------------------------------------------------ văn bản thật trong data/raw (nghiệm thu T2)


def _registry_docs():
    cfg = load_config()
    reg = cfg.path(cfg.paths.registry)
    if not reg.exists():
        return []
    raw = cfg.path(cfg.paths.raw_dir)
    return [(m, find_raw_file(raw, m)) for m in load_registry(reg) if m.so_dieu is not None]


@pytest.mark.parametrize("meta,path", _registry_docs(), ids=lambda x: getattr(x, "doc_id", ""))
def test_registry_article_count(meta: DocMeta, path: Path | None):
    if path is None:
        pytest.skip(f"chưa có file cho {meta.doc_id} trong data/raw")
    assert len(parse_file(path).articles) == meta.so_dieu
