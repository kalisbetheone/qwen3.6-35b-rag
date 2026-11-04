# CLAUDE.md

Kế hoạch và tiêu chí nghiệm thu từng task (T1–T10): @docs/PLAN.md (mục 9.2).

## Quy ước
- Mọi tham số (top-k, τ, tên model, đường dẫn) đọc từ `config.yaml` qua `common.config.load_config()`; không hard-code. Ablation dùng `overrides`.
- Prompt nằm trong `prompts/*.md`.
- `chunk_id` dạng `<doc_id>_d<Điều>[_k<Khoản>][_<điểm>]`, ổn định — là khoá trích dẫn và khoá đánh giá (so ở mức Điều).
- Văn bản `internal` chỉ là dữ liệu giả lập tự viết; không đưa văn bản nội bộ thật vào repo.
- Chạy script đánh giá dạng module từ gốc repo: `python -m eval.run_retrieval`.

## Lệnh
- Test: `python -m pytest`
- Ingest: `python -m ingest.run_ingest --strict`
- Index CPU: `python scripts/build_index.py --no-dense`
- API nhẹ: `USE_DENSE=false USE_RERANK=false LLM_PROVIDER=echo uvicorn api.main:app --port 7860`
- Sửa notebook: sửa `scripts/make_notebooks.py` rồi chạy lại (không sửa .ipynb trực tiếp)
- Đồng bộ Drive: `scripts/sync_to_drive.ps1` (Colab: `/content/drive/MyDrive/vilex-annd`)

## Môi trường
- Laptop: Windows, Python 3.10, Node.js 26 (cài 03/11/2026). Chạy thử toàn bộ không GPU: `python scripts/dev_server.py`.
- Vai trò: `hoc_vien` (public) và `giang_vien` (public + internal, được upload). Tài khoản mặc định ở `auth.seed_users`.
- Colab: vLLM + Qwen3.6-35B-A3B bản Q4 (AWQ cộng đồng `QuantTrio/Qwen3.6-35B-A3B-AWQ`), bge-m3, bge-reranker-v2-m3.
