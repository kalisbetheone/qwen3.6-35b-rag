import pytest

from retrieval.fusion import rrf


def test_rrf_scores_and_order():
    bm25 = ["a", "b", "c"]
    dense = ["c", "a", "d"]
    out = dict(rrf([bm25, dense], k=60))
    assert out["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert out["c"] == pytest.approx(1 / 63 + 1 / 61)
    assert out["d"] == pytest.approx(1 / 63)
    assert [d for d, _ in rrf([bm25, dense], k=60)] == ["a", "c", "b", "d"]


def test_rrf_top_n_and_ties_stable():
    out = rrf([["x", "y"], ["y", "x"]], k=60, top_n=1)  # hoà điểm -> giữ thứ tự xuất hiện đầu
    assert out == [("x", pytest.approx(1 / 61 + 1 / 62))]
    assert len(rrf([["a"], ["b"]], top_n=5)) == 2


def test_rrf_single_and_empty():
    assert [d for d, _ in rrf([["p", "q"]])] == ["p", "q"]
    assert rrf([]) == [] and rrf([[], []]) == []


def test_rrf_agreement_beats_single_top():
    # tài liệu được cả hai hệ xếp hạng 2 thắng tài liệu chỉ một hệ xếp hạng 1
    out = rrf([["solo", "both"], ["other", "both"]], k=60)
    assert out[0][0] == "both"
