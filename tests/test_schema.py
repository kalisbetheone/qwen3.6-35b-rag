import pytest
from pydantic import ValidationError

from common.config import load_config
from common.schema import Chunk

SAMPLE = dict(
    chunk_id="nd125-2026_d7_k2", doc_id="nd125-2026", so_hieu="125/2026/NĐ-CP", loai="Nghị định",
    dieu="7", khoan=2, citation_label="Khoản 2 Điều 7, NĐ 125/2026/NĐ-CP",
    text_for_embed="[NĐ 125/2026/NĐ-CP > Điều 7 > Khoản 2]\n2. ...", text_display="2. ...",
    n_tokens=3, parent_article_id="nd125-2026_d7",
)


def test_chunk_valid():
    c = Chunk(**SAMPLE)
    assert c.access_level == "public" and c.hieu_luc == "con_hieu_luc"


@pytest.mark.parametrize("cid", ["nd125-2026_d7", "nd125-2026_d7_k2_a", "nd125-2026_d7_k2_a-dd", "luat93-2025_d12a"])
def test_chunk_id_formats(cid):
    Chunk(**{**SAMPLE, "chunk_id": cid})


@pytest.mark.parametrize("bad", [{"chunk_id": "ND125 d7"}, {"access_level": "secret"}, {"hieu_luc": "x"}])
def test_chunk_invalid(bad):
    with pytest.raises(ValidationError):
        Chunk(**{**SAMPLE, **bad})


def test_config_loads_and_env_override(monkeypatch):
    cfg = load_config()
    assert cfg.retrieval.rrf_k == 60
    monkeypatch.setenv("TOP_K", "3")
    monkeypatch.setenv("USE_DENSE", "false")
    cfg = load_config()
    assert cfg.retrieval.top_k == 3 and cfg.retrieval.use_dense is False
    assert cfg.allowed_levels("giang_vien") == ["public", "internal"]
    assert cfg.index_path.name == "bge-m3"
