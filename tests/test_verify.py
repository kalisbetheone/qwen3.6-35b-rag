from generation.verify import clean_invalid, parse_cites, split_sentences, verify

SOURCES = ["Trưởng nhóm được giảm đến 50% định mức giờ chuẩn.", "Giảng viên phải nghiên cứu 10% thời gian.",
           "Nghị định có hiệu lực từ ngày 01/02/2099."]


def test_parse_cite_forms():
    assert parse_cites("a [1] b [2, 3] c [4;5]") == [1, 2, 3, 4, 5]


def test_out_of_range_labels_removed():
    text, invalid = clean_invalid("Ý một [1]. Ý hai [7]. Ý ba [2, 9].", n_sources=3)
    assert text == "Ý một [1]. Ý hai. Ý ba [2]."
    assert invalid == [7, 9]


def test_sentence_split_with_citations_and_lists():
    ans = ("Trưởng nhóm được giảm đến 50% định mức [1]. Giảng viên phải dành 10% thời gian [2].\n"
           "Các điểm chính:\n- Hiệu lực từ 01/02/2099 [3].\n1. Một ý không có nhãn nhưng có số 12 tháng.")
    s = split_sentences(ans)
    assert [x.cites for x in s] == [[1], [2], [], [3], []]
    assert s[0].text.endswith("[1].") and s[3].text.startswith("Hiệu lực")
    assert ans[s[1].start:s[1].end] == s[1].text


def test_period_then_label_attached_to_previous_sentence():
    s = split_sentences("Câu thứ nhất có căn cứ. [1] Câu thứ hai cũng vậy. [2]")
    assert [x.cites for x in s] == [[1], [2]]


def test_unsupported_and_grounding_score():
    ans = "Trưởng nhóm được giảm đến 50% định mức giờ chuẩn [1]. Thời hạn nộp là 30 ngày kể từ khi có thông báo."
    r = verify(ans, SOURCES)
    assert r.citations_used == [1]
    assert [f["type"] for f in r.flags] == ["unsupported"]
    assert r.flags[0]["sentence_idx"] == 1
    assert r.grounding_score == 0.5


def test_weak_with_scorer():
    def scorer(pairs):  # giả lập reranker: chỉ cặp có chung chữ "50%" mới điểm cao
        return [0.9 if "50%" in a and "50%" in b else 0.05 for a, b in pairs]

    ans = "Trưởng nhóm được giảm đến 50% định mức [1]. Giảng viên được nghỉ phép sáu tháng để học tập [2]."
    r = verify(ans, SOURCES, scorer=scorer, weak_threshold=0.2)
    assert [(f["sentence_idx"], f["type"]) for f in r.flags] == [(1, "weak")]
    assert r.grounding_score == 0.5
    assert r.sentences[0].support == 0.9


def test_lead_in_and_legal_refs_not_flagged():
    ans = ("Theo Điều 6 NĐ 125/2026/NĐ-CP:\n- Nhóm có ít nhất 03 thành viên [1].\n"
           "Nội dung này được quy định tại khoản 2 Điều 7 Nghị định 125/2026/NĐ-CP.\n"
           "Thời hạn nộp là 30 ngày kể từ khi có thông báo.")
    r = verify(ans, SOURCES)
    assert [(f["sentence_idx"], f["type"]) for f in r.flags] == [(3, "unsupported")]  # chỉ câu có số liệu thật
    assert r.grounding_score == 1 / 3  # câu dẫn ":" không tính; 1/3 câu khẳng định có nhãn


def test_labels_with_clause_hints():
    text, invalid = clean_invalid("Ý một [1, 3a]. Ý hai [2, 2đ]. Ý ba [1, Khoản 2]. Ý bốn [7, 1b].", n_sources=3)
    assert text == "Ý một [1]. Ý hai [2]. Ý ba [1]. Ý bốn." and invalid == [7]
    ans = "- Cơ sở có nhóm nghiên cứu mạnh được ưu tiên 01 lần [1, 3a].\n- Nhiệm vụ có 02 doanh nghiệp [2, 2đ]."
    r = verify(ans, SOURCES)
    assert not r.flags and r.grounding_score == 1.0 and r.citations_used == [1, 2]


def test_refusal_detected():
    r = verify("Các văn bản hiện có không quy định về vấn đề này.", SOURCES)
    assert r.is_refusal and r.grounding_score is None and not r.flags
