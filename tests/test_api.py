"""Kiểm thử API ở chế độ nhẹ: BM25-only + LLM 'echo' (không cần GPU, không cần vLLM)."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from common.config import ChunkingCfg, load_config, model_slug
from common.schema import DocMeta
from ingest.chunker import Chunker
from ingest.parser import parse_file
from retrieval.bm25 import BM25Index
from retrieval.store import ChunkStore

from .conftest import FIXTURES, ROOT

PW = "abc123"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import api.deps as deps
    from api.main import app

    base = tmp_path_factory.mktemp("api")
    pub = DocMeta(doc_id="nd999-2099", so_hieu="999/2099/NĐ-CP", loai="Nghị định", ten="Nghị định mẫu")
    internal = DocMeta(doc_id="qc-mau-noibo-01", so_hieu="01/QC-MẪU", loai="Quy chế", access_level="internal")
    ch = Chunker(ChunkingCfg())
    c1, a1 = ch.chunk_document(pub, parse_file(FIXTURES / "nd_mau_kiem_thu.txt"))
    c2, a2 = ch.chunk_document(internal, parse_file(ROOT / "data" / "raw" / "qc-mau-noibo-01.txt"))
    cfg = load_config(overrides={
        "retrieval.use_dense": False, "retrieval.use_rerank": False, "llm.provider": "echo",
        "paths.index_dir": str(base / "index"), "paths.log_dir": str(base / "logs"),
        "paths.app_dir": str(base / "app"), "paths.chunks": str(base / "chunks.jsonl"),
        "paths.articles": str(base / "articles.jsonl"),
    })
    out = base / "index" / model_slug(cfg.models.embed_model)
    store = ChunkStore(c1 + c2, a1 + a2, [pub, internal])
    store.save(out)
    BM25Index("underthesea").build([c.text_for_embed for c in store.chunks]).save(out / "bm25")
    with TestClient(app) as c:
        deps.init_services(cfg)  # lifespan đã init bằng config mặc định -> đặt lại
        yield c, base


def login(c, username, password=PW):
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def hv(client):
    return login(client[0], "hocviens1")


@pytest.fixture(scope="module")
def gv(client):
    return login(client[0], "giangviens1")


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


# ------------------------------------------------------------ đăng nhập


def test_seed_accounts_and_login(client):
    c, base = client
    users = json.loads((base / "app" / "users.json").read_text(encoding="utf-8"))
    assert set(users) >= {"hocviens1", "giangviens1"}
    assert all("abc123" not in json.dumps(u) for u in users.values())  # không lưu mật khẩu rõ
    assert c.post("/api/auth/login", json={"username": "hocviens1", "password": "sai"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "khongco", "password": PW}).status_code == 401
    me = c.get("/api/auth/me", headers=login(c, "HocVienS1")).json()  # tên đăng nhập không phân biệt hoa thường
    assert me["role"] == "hoc_vien" and me["can_upload"] is False
    assert c.get("/api/auth/me", headers=login(c, "giangviens1")).json()["can_upload"] is True


def test_requires_auth_and_rejects_forged_token(client):
    c, _ = client
    assert c.post("/api/chat", json={"question": "abc"}).status_code == 401
    assert c.get("/api/documents").status_code == 401
    assert c.get("/api/documents", headers={"Authorization": "Bearer abc.def"}).status_code == 401
    good = login(c, "hocviens1")["Authorization"].split()[1]
    payload, sig = good.split(".")
    import base64

    forged = base64.urlsafe_b64encode(json.dumps({"sub": "giangviens1", "role": "giang_vien",
                                                  "exp": 9999999999}).encode()).rstrip(b"=").decode()
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}.{sig}"}).status_code == 401


def test_health_and_meta_public(client):
    c, _ = client
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/api/meta").json()["suggested_questions"]


# ------------------------------------------------------------ hỏi–đáp + hội thoại


def test_chat_creates_conversation_and_saves_turns(client, hv):
    c, base = client
    r = c.post("/api/chat", headers=hv, json={"question": "Trưởng nhóm nghiên cứu được giảm bao nhiêu giờ chuẩn?"})
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "sources" and names[-1] == "done" and "token" in names
    done = events[-1][1]
    conv_id = done["conversation_id"]
    assert done["citations_used"] and set(done["latency_ms"]) >= {"retrieve", "rerank", "generate"}

    conv = c.get(f"/api/conversations/{conv_id}", headers=hv).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["title"].startswith("Trưởng nhóm") and conv["messages"][1]["sources"]

    # lượt 2 trong cùng hội thoại
    parse_sse(c.post("/api/chat", headers=hv, json={"question": "Còn hiệu lực từ ngày nào?",
                                                     "conversation_id": conv_id}).text)
    assert len(c.get(f"/api/conversations/{conv_id}", headers=hv).json()["messages"]) == 4
    log = (base / "logs" / "queries.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(log[-1])["user"] == "hocviens1"


def test_conversation_crud_and_isolation(client, hv, gv):
    c, _ = client
    new = c.post("/api/conversations", headers=hv, json={}).json()
    assert new["title"] == "Cuộc trò chuyện mới"
    assert any(x["id"] == new["id"] for x in c.get("/api/conversations", headers=hv).json())
    assert c.patch(f"/api/conversations/{new['id']}", headers=hv, json={"title": "Đổi tên"}).json()["title"] == "Đổi tên"
    # người khác không xem được
    assert c.get(f"/api/conversations/{new['id']}", headers=gv).status_code == 404
    assert c.get("/api/conversations/../../users", headers=hv).status_code == 404
    assert c.delete(f"/api/conversations/{new['id']}", headers=hv).status_code == 204
    assert c.get(f"/api/conversations/{new['id']}", headers=hv).status_code == 404


def test_search_mode_direct_and_refusal(client, hv):
    c, _ = client
    ev = parse_sse(c.post("/api/chat", headers=hv, json={"question": "Điều 6 Nghị định 999/2099", "mode": "search"}).text)
    assert [e for e, _ in ev] == ["sources", "done"] and ev[0][1]["sources"][0]["dieu"] == "6"
    done = parse_sse(c.post("/api/chat", headers=hv, json={"question": "xyzzy qwerty"}).text)[-1][1]
    assert done["no_evidence"] and "không quy định" in done["answer"]


def test_role_filter_from_token(client, hv, gv):
    c, _ = client
    assert {d["doc_id"] for d in c.get("/api/documents", headers=hv).json()} == {"nd999-2099"}
    assert {d["doc_id"] for d in c.get("/api/documents", headers=gv).json()} == {"nd999-2099", "qc-mau-noibo-01"}
    assert c.get("/api/article/qc-mau-noibo-01/5", headers=hv).status_code == 404
    assert len(c.get("/api/article/qc-mau-noibo-01/5", headers=gv).json()["clauses"]) == 3
    # học viên hỏi trúng nội dung nội bộ cũng không thấy nguồn nội bộ
    ev = parse_sse(c.post("/api/chat", headers=hv, json={"question": "Đề tài cấp cơ sở được gia hạn bao lâu?"}).text)
    assert all(s["access_level"] == "public" for s in ev[0][1]["sources"])


def test_feedback(client, hv):
    c, base = client
    assert c.post("/api/feedback", headers=hv, json={"query_id": "abc", "rating": 1}).status_code == 204


# ------------------------------------------------------------ thêm dữ liệu


def _wait(c, headers, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{job_id}", headers=headers).json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.3)
    raise TimeoutError(job_id)


def test_upload_permissions_and_validation(client, hv, gv):
    c, _ = client
    f = {"file": ("a.txt", "nội dung".encode(), "text/plain")}
    assert c.post("/api/documents/upload", headers=hv, files=f).status_code == 403
    r = c.post("/api/documents/upload", headers=gv, files={"file": ("cu.doc", b"x", "application/msword")})
    assert r.status_code == 400 and ".docx" in r.json()["detail"]
    assert c.post("/api/documents/upload", headers=gv, files={"file": ("a.exe", b"x", "x")}).status_code == 400


def test_upload_unstructured_doc_then_delete(client, hv, gv):
    c, base = client
    text = ("HƯỚNG DẪN NỘP HỒ SƠ GIẢI THƯỞNG SINH VIÊN\n"
            "Sinh viên nộp hồ sơ dự thi giải thưởng nghiên cứu khoa học trước ngày 15 tháng 3 hằng năm tại phòng quản lý khoa học.\n"
            "1. CHUẨN BỊ HỒ SƠ\n"
            "Hồ sơ gồm báo cáo tổng kết đề tài, tóm tắt kết quả và xác nhận của giảng viên hướng dẫn.\n")
    r = c.post("/api/documents/upload", headers=gv,
               files={"file": ("huong-dan.txt", text.encode("utf-8"), "text/plain")},
               data={"loai": "Tài liệu", "ten": "Hướng dẫn nộp hồ sơ giải thưởng", "access_level": "public"})
    assert r.status_code == 200, r.text
    job = _wait(c, gv, r.json()["id"])
    assert job["status"] == "done", job
    doc_id = job["doc_id"]
    docs = {d["doc_id"]: d for d in c.get("/api/documents", headers=hv).json()}
    assert docs[doc_id]["source"] == "upload" and docs[doc_id]["uploaded_by"] == "giangviens1"
    # tìm được ngay, nhãn dùng "Phần" vì không có cấu trúc Điều
    ev = parse_sse(c.post("/api/chat", headers=hv, json={"question": "Hạn nộp hồ sơ giải thưởng nghiên cứu khoa học sinh viên",
                                                         "mode": "search"}).text)
    top = ev[0][1]["sources"][0]
    assert top["doc_id"] == doc_id and top["citation_label"].startswith("Phần")
    reg = (base / "app" / "uploads" / "registry.csv").read_text(encoding="utf-8-sig")
    assert reg.count(f"\n{doc_id},") == 1
    assert doc_id in (base / "chunks.jsonl").read_text(encoding="utf-8")  # chunks.jsonl đồng bộ để ingest sau cho cùng kết quả

    assert c.delete("/api/documents/nd999-2099", headers=gv).status_code == 400  # không xoá văn bản kho gốc
    assert c.delete(f"/api/documents/{doc_id}", headers=gv).status_code == 204
    assert doc_id not in {d["doc_id"] for d in c.get("/api/documents", headers=gv).json()}


def test_upload_structured_internal_doc(client, hv, gv):
    c, _ = client
    data = (FIXTURES / "nd_mau_kiem_thu.txt").read_bytes()
    r = c.post("/api/documents/upload", headers=gv, files={"file": ("nd-mau-2.txt", data, "text/plain")},
               data={"loai": "Nghị định", "so_hieu": "998/2099/NĐ-CP", "access_level": "internal"})
    job = _wait(c, gv, r.json()["id"])
    assert job["status"] == "done" and job["n_articles"] == 7 and job["unit"] == "Điều"
    assert job["doc_id"] in {d["doc_id"] for d in c.get("/api/documents", headers=gv).json()}
    assert job["doc_id"] not in {d["doc_id"] for d in c.get("/api/documents", headers=hv).json()}
    c.delete(f"/api/documents/{job['doc_id']}", headers=gv)
