# ViLex-ANND — Trợ lý hỏi–đáp văn bản KH,CN&ĐMST (RAG on-premise)

Kế hoạch đầy đủ: [docs/PLAN.md](docs/PLAN.md). Mọi tham số (top-k, τ, tên model) nằm trong [config.yaml](config.yaml).

## Trên laptop (CPU)

```bash
pip install -r requirements.txt
python -m pytest                              # 76 test: parser, chunker, truy xuất, verify, API, đăng nhập, upload
ruff check .                                  # lint (cấu hình trong pyproject.toml)
python -m ingest.run_ingest --strict          # data/raw + data/registry.csv -> data/processed/ (không lưu trong git)
python scripts/build_index.py --no-dense      # index BM25 (không cần GPU)
cd frontend && npm install && npm run build   # giao diện -> frontend/dist
```

Chạy thử cả hệ thống không cần GPU (BM25 + LLM giả "echo" trích câu đầu của nguồn), mở http://localhost:7860:

```bash
python scripts/dev_server.py
```

## Tài khoản và phân quyền

Tạo sẵn khi khởi động lần đầu (khai báo ở `auth.seed_users` trong `config.yaml`; mật khẩu được băm PBKDF2 vào `appdata/users.json`):

| Tài khoản | Vai trò | Được xem | Thêm/xoá dữ liệu |
|---|---|---|---|
| `hocviens1` | Học viên | văn bản `public` | không |
| `giangviens1` | Giảng viên | `public` + `internal` | có |

Đây là tài khoản **demo** (mật khẩu mặc định trong `config.yaml`); đổi mật khẩu hoặc xoá khỏi `seed_users` trước khi triển khai thật.
Vai trò lấy từ token phía server (client không tự khai báo được). Hội thoại lưu theo người dùng ở `appdata/conversations/`.
Văn bản giảng viên tải lên (Word/PDF/TXT) lưu ở `appdata/uploads/`, được cập nhật vào index ngay và được
`run_ingest` gộp cùng kho gốc ở các lần chạy sau. `appdata/` không đồng bộ từ laptop lên Drive.

Đồng bộ code lên Drive (Colab đọc ở `/content/drive/MyDrive/vilex-annd`):

```bash
powershell -ExecutionPolicy Bypass -File scripts\sync_to_drive.ps1
```

## Trên Colab (A100 40GB trở lên)

VRAM thực tế: checkpoint AWQ nặng 25,5 GB (tháp ảnh, attention, shared expert, layer 0 vẫn ở FP16). vLLM được cấp
~30 GiB tuyệt đối với `--max-num-seqs 16 --max-num-batched-tokens 4096` và tắt đầu vào ảnh; embedding + reranker ~5 GiB.
Tổng ~35 GiB → chạy được trên A100 40GB. GPU 24 GB chỉ chạy được bằng llama.cpp GGUF IQ4_XS + embedding trên CPU.

1. `notebooks/colab_serve.ipynb` — ingest → build index → vLLM (Qwen3.6-35B-A3B Q4) → build frontend → FastAPI → tunnel → nghiệm thu T6/T7.
2. `notebooks/colab_eval.ipynb` — index bge-m3 + DEk21 → nháp câu hỏi → **duyệt tay** → dò τ → ablation → có/không RAG → report.

## Thêm văn bản

1. Lưu file `.docx`/`.pdf` (có lớp text) vào `data/raw/`, tên `<doc_id>.docx` (hoặc ghi cột `file`).
2. Thêm dòng vào `data/registry.csv`; **đếm tay số Điều** điền vào `so_dieu` (dùng để kiểm parser).
3. `python -m ingest.run_ingest --strict` phải không báo `LỆCH`, rồi đồng bộ lên Drive.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `common/` | config (yaml + biến môi trường), schema Pydantic |
| `ingest/` | parser Chương→Mục→Điều→Khoản→Điểm, chunker, run_ingest |
| `retrieval/` | router (tra trực tiếp), bm25, dense, fusion (RRF), rerank, pipeline |
| `generation/` | llm_client (vLLM/llama.cpp/echo), prompt_builder, verify (hậu kiểm trích dẫn), service |
| `api/` | FastAPI + SSE, đăng nhập (auth), hội thoại, thêm dữ liệu (uploads), log truy vấn JSONL |
| `eval/` | bộ câu hỏi (qa_set.jsonl), run_retrieval, run_e2e, make_report |
| `frontend/` | Vite + React + TS + Tailwind |
| `prompts/` | prompt tiếng Việt (không hard-code trong code) |

`data/raw/qc-mau-noibo-01.txt` là **dữ liệu giả lập** (access_level `internal`) chỉ để minh hoạ phân quyền.
