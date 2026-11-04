from common.config import ROOT
from generation.llm_client import EchoLLM, _ThinkFilter
from generation.prompt_builder import PromptBuilder
from retrieval.store import Source


def _run(chunks):
    f = _ThinkFilter()
    return "".join(f.feed(c) for c in chunks) + f.flush()


def test_think_filter_split_tags():
    assert _run(["<thi", "nk>suy nghĩ", " dài</th", "ink>\n\nTrả lời [1]."]) == "Trả lời [1]."
    assert _run(["Không có ", "thẻ nào", " cả."]) == "Không có thẻ nào cả."
    assert _run(["a < b và ", "c"]) == "a < b và c"


def _src(text="Điều 6. Giảm định mức\nTrưởng nhóm được giảm đến 50% định mức."):
    return Source(chunk_ids=["x_d6"], doc_id="nd109-2022", so_hieu="109/2022/NĐ-CP", dieu="6", khoan=None, diem=None,
                  citation_label="Điều 6, NĐ 109/2022/NĐ-CP", header="[NĐ 109/2022/NĐ-CP > Điều 6: Giảm định mức]",
                  text=text, score=0.9)


def test_prompt_contains_numbered_sources_and_status():
    pb = PromptBuilder(ROOT / "prompts", status_note=lambda d: "hết hiệu lực" if d == "nd109-2022" else "")
    msgs = pb.answer_messages("Giảm bao nhiêu?", [_src()], missing_refs=["Điều 99 NĐ 125/2026/NĐ-CP"])
    assert msgs[0]["role"] == "system" and "[số]" in msgs[0]["content"]
    u = msgs[1]["content"]
    assert u.startswith("NGUỒN:\n[1] [NĐ 109/2022/NĐ-CP > Điều 6") and "(Tình trạng: hết hiệu lực)" in u
    assert "Điều 99 NĐ 125/2026/NĐ-CP" in u and u.endswith("CÂU HỎI: Giảm bao nhiêu?\nTRẢ LỜI:")
    c = pb.condense_messages([{"role": "user", "content": "Điều 7 NĐ 125?"}, {"role": "assistant", "content": "…"}],
                             "còn Điều 9 thì sao?")
    assert "CÂU HỎI MỚI: còn Điều 9 thì sao?" in c[0]["content"]


def test_echo_llm_cites_sources():
    out = EchoLLM().complete([], sources=[_src()])
    assert out.endswith("Trưởng nhóm được giảm đến 50% định mức [1].")
    assert EchoLLM().complete([], sources=[]) == EchoLLM.REFUSAL
