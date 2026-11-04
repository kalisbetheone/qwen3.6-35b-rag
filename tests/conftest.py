import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.schema import DocMeta  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def sample_meta() -> DocMeta:
    return DocMeta(doc_id="nd999-2099", so_hieu="999/2099/NĐ-CP", loai="Nghị định",
                   ten="Quy định mẫu dùng để kiểm thử", so_dieu=7, alias="Nghị định 999;NĐ 999")


@pytest.fixture
def sample_doc():
    from ingest.parser import parse_file

    return parse_file(FIXTURES / "nd_mau_kiem_thu.txt")


@pytest.fixture
def sample_chunks(sample_meta, sample_doc):
    from common.config import ChunkingCfg
    from ingest.chunker import Chunker

    return Chunker(ChunkingCfg()).chunk_document(sample_meta, sample_doc)
