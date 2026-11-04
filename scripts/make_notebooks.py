"""Sinh notebooks/colab_serve.ipynb và colab_eval.ipynb (sửa nội dung cell ở đây rồi chạy lại script)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETUP = r'''# 1. Mount Drive + vào thư mục dự án
from google.colab import drive
drive.mount('/content/drive')
PROJECT = '/content/drive/MyDrive/vilex-annd'
%cd {PROJECT}
import sys; sys.path.insert(0, PROJECT); sys.path.insert(0, PROJECT + '/scripts')
!nvidia-smi --query-gpu=name,memory.total --format=csv'''

INSTALL = r'''# 2. Cài thư viện (~3–6 phút). vLLM cài kèm torch tương thích.
!pip install -q -U vllm
!pip install -q -r requirements-colab.txt
import importlib, colab_utils; importlib.reload(colab_utils); from colab_utils import *'''

LLM_CFG = r'''# 3. Chọn LLM. Bản Q4 cộng đồng (Qwen chưa phát hành AWQ chính thức) — kiểm tra model card trước khi dùng.
LLM_REPO    = "QuantTrio/Qwen3.6-35B-A3B-AWQ"        # AWQ 4-bit, nhiều lượt tải nhất
# LLM_REPO  = "palmfuture/Qwen3.6-35B-A3B-GPTQ-Int4" # phương án Q4 khác
# LLM_REPO  = "Qwen/Qwen3.6-35B-A3B-FP8"             # chỉ để đo Q4 vs FP8 trên GPU 80 GB
SERVED_NAME = "qwen3.6-35b-a3b"                      # = llm.model trong config.yaml
MAX_LEN     = 16384
# vLLM được cấp ~30 GiB tuyệt đối (trọng số 23,7 GiB + activation + CUDA graph + cache 16 chuỗi);
# phần còn lại (~5 GiB) cho bge-m3 + reranker của API. A100 40GB -> 0.75, 80GB -> 0.38, 96GB -> 0.31.
GPU_UTIL    = auto_gpu_util()
print("gpu_memory_utilization =", GPU_UTIL, "| cờ tiết kiệm VRAM:", VLLM_LEAN_ARGS)'''

INGEST = r'''# 4. Ingest + build index (chạy TRƯỚC khi bật vLLM để dùng hết GPU).
# Ingest chỉ mất vài giây; index chỉ build lại khi chunks.jsonl thay đổi (thêm/sửa văn bản).
!python -m ingest.run_ingest --strict
!python scripts/build_index.py --if-stale'''

VLLM = r'''# 5. Khởi động vLLM chạy nền (lần đầu tải ~25 GB trọng số, 3–10 phút). Log: /content/logs/vllm.log
# Mặc định thêm: --max-num-seqs 16 (mỗi chuỗi giữ ~33 MiB trạng thái Gated DeltaNet; mặc định 256 chuỗi là ~8 GiB),
# --max-num-batched-tokens 4096, và tắt đầu vào ảnh/video (model là bản đa phương thức, không cần cho tra cứu).
# Lỗi thì in thẳng dòng nguyên nhân; chạy xong in bảng VRAM thực tế.
vllm_proc = start_vllm(LLM_REPO, SERVED_NAME, max_len=MAX_LEN, gpu_util=GPU_UTIL)'''

VLLM_SMOKE = r'''# Kiểm tra nhanh LLM (thinking đã tắt qua chat_template_kwargs)
import httpx
r = httpx.post("http://localhost:8000/v1/chat/completions", timeout=120, json={
    "model": SERVED_NAME, "messages": [{"role": "user", "content": "Chào bạn, trả lời một câu ngắn bằng tiếng Việt."}],
    "max_tokens": 64, "chat_template_kwargs": {"enable_thinking": False}})
print(r.json()["choices"][0]["message"]["content"])'''

FRONTEND = r'''# 6. Build frontend (Vite) ngoài Drive rồi chép dist về — chỉ cần làm lại khi sửa code frontend
build_frontend(PROJECT, force=False)'''

API = r'''# 7. Chạy FastAPI nền ở cổng 7860 (phục vụ cả frontend). Log: /content/logs/api.log
API_ENV = {"LLM_BASE_URL": "http://localhost:8000/v1", "LLM_MODEL": SERVED_NAME, "HF_HOME": "/content/hf_cache"}
api_proc = start_api(PROJECT, API_ENV)
!curl -s localhost:7860/api/health | python -m json.tool
vram_report()   # VRAM thực tế của vLLM + API — số liệu cho mục "Điều kiện, nguồn lực"'''

TUNNEL = r'''# 8. Mở tunnel cloudflared (không cần tài khoản) -> in URL demo
tunnel_proc, URL = start_tunnel(7860)'''

ACCEPT = r'''# 9. Nghiệm thu T6/T7: đủ 4 loại event SSE, câu trong phạm vi có [n], câu ngoài phạm vi bị từ chối
TOKEN = login("giang_vien")   # tài khoản mặc định trong config.yaml (auth.seed_users)
!curl -sN -X POST localhost:7860/api/chat -H 'Content-Type: application/json' -H "Authorization: Bearer {TOKEN}" -d '{"question":"Điều 7 Nghị định 125/2026/NĐ-CP quy định gì?"}' | head -c 1500
QUESTIONS = [
    "Điều 7 Nghị định 125/2026/NĐ-CP quy định gì?",
    "Giảng viên tham gia nghiên cứu khoa học được giảm định mức giờ chuẩn như thế nào?",
    "Sinh viên làm nghiên cứu khoa học được hỗ trợ gì?",
    "Nghị định 109/2022/NĐ-CP còn hiệu lực không?",
    "Lệ phí trước bạ khi mua ô tô là bao nhiêu?",   # ngoài phạm vi -> phải từ chối
]
import re
for q in QUESTIONS:
    e = ask(q)
    d = e.get("done", {})
    ans = d.get("answer", e.get("error"))
    print("="*100, "\nQ:", q, "\n", ans, f"\n-> nhãn: {re.findall(r'\[\d+', ans or '')} | no_evidence={d.get('no_evidence')} "
          f"| grounding={d.get('grounding_score')} | latency={d.get('latency_ms')}")'''

RESTART_API = r'''# (Khi sửa code backend/config) khởi động lại API mà không phải tắt vLLM
stop(api_proc); api_proc = start_api(PROJECT, API_ENV)'''

LLAMACPP = r'''# DỰ PHÒNG: vLLM lỗi với checkpoint Q4 -> llama.cpp GGUF (API kiểu OpenAI, backend không đổi gì ngoài URL)
# Build ~5–8 phút. GGUF lượng tử hoá cả attention/expert nên nhỏ hơn AWQ: Q4_K_M ~22 GB, IQ4_XS ~19 GB.
# GPU 24 GB (L4): dùng IQ4_XS và chạy embedding/reranker trên CPU (API_ENV["DEVICE"] = "cpu").
USE_LLAMACPP = False
if USE_LLAMACPP:
    try: stop(vllm_proc)
    except NameError: pass
    !test -d /content/llama.cpp || git clone -q --depth 1 https://github.com/ggml-org/llama.cpp /content/llama.cpp
    !cd /content/llama.cpp && cmake -B build -DGGML_CUDA=ON -DLLAMA_CURL=ON > /dev/null && cmake --build build -j --target llama-server > /dev/null
    import subprocess
    llama_proc = colab_utils._popen("/content/llama.cpp/build/bin/llama-server -hf unsloth/Qwen3.6-35B-A3B-GGUF:Q4_K_M "
                                    f"--alias {SERVED_NAME} --port 8000 -c {MAX_LEN} -ngl 99 --jinja", "llama.log",
                                    env={"LLAMA_CACHE": "/content/hf_cache/llama"})
    wait_http("http://localhost:8000/v1/models", timeout=1800, proc=llama_proc, log_name="llama.log")'''

# ---------------------------------------------------------------- eval

EVAL_INTRO = """# ViLex-ANND — Đánh giá (T9)
Thứ tự: build index cho 2 model embedding → bật LLM → (sinh nháp câu hỏi → **bạn duyệt tay** → lưu `eval/qa_set.jsonl`)
→ dò τ trên dev → ablation truy xuất trên test → có/không RAG → (tuỳ chọn) FP8 → `make_report`.
Mọi con số trong bài lấy từ `eval/results/`."""

EVAL_INDEX = r'''# Index cho cả bge-m3 và DEk21 (ablation). Chạy trước khi bật vLLM.
!python -m ingest.run_ingest --strict
for model in ["BAAI/bge-m3", "huyydangg/DEk21_hcmute_embedding"]:
    !EMBED_MODEL={model} python scripts/build_index.py --if-stale
!ls -la index/*'''

EVAL_DRAFT = r'''# Sinh NHÁP câu hỏi (chỉ khi chưa có qa_set.jsonl). Sau đó tải eval/qa_draft.jsonl về, duyệt/sửa từng câu,
# sửa gold_chunk_ids nếu cần, rồi lưu thành eval/qa_set.jsonl trên Drive.
import os
if not os.path.exists("eval/qa_set.jsonl"):
    !LLM_MODEL={SERVED_NAME} python scripts/gen_qa_draft.py
else:
    print("Đã có eval/qa_set.jsonl")'''

EVAL_TAU = r'''# Dò ngưỡng τ trên dev (hybrid + rerank với τ=0) -> sửa retrieval.rerank_threshold trong config.yaml
!python -m eval.run_retrieval --split dev --calibrate --configs hybrid_rerank
!cat eval/results/tau_calibration.csv'''

EVAL_RETR = r'''# Ablation truy xuất trên test (6 cấu hình)
!python -m eval.run_retrieval --split test'''

EVAL_E2E = r'''# Có RAG vs không RAG (Q4). Xong thì CHẤM TAY cột score (0/1/2) và citation_ok (0/1) trong eval/results/e2e_grading_*.csv
!LLM_MODEL={SERVED_NAME} python -m eval.run_e2e --split test --label q4'''

EVAL_FP8 = r'''# Tuỳ chọn (GPU 80 GB): Q4 vs FP8 — tắt vLLM Q4, bật bản FP8, chạy lại
RUN_FP8 = False
if RUN_FP8:
    stop(vllm_proc)
    # FP8: trọng số ~35–37 GB (gần gấp rưỡi bản AWQ) -> ngân sách ~44 GiB, chỉ vừa GPU 80 GB
    vllm_proc = start_vllm("Qwen/Qwen3.6-35B-A3B-FP8", SERVED_NAME, max_len=MAX_LEN,
                           gpu_util=auto_gpu_util(budget_gib=44))
    !LLM_MODEL={SERVED_NAME} python -m eval.run_e2e --split test --label fp8'''

EVAL_REPORT = r'''# Gộp kết quả -> eval/results/report.md + 2 biểu đồ (chạy lại sau khi chấm tay)
!python -m eval.make_report
from IPython.display import Markdown, Image, display
display(Markdown(open("eval/results/report.md", encoding="utf-8").read()))'''


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": src.splitlines(keepends=True)}


def notebook(cells: list[dict]) -> dict:
    return {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "A100"},
                         "kernelspec": {"name": "python3", "display_name": "Python 3"},
                         "language_info": {"name": "python"}}}


SERVE = [
    md("# ViLex-ANND — Chạy demo trên Colab\nRuntime → Change runtime type → **A100/H100**. Chạy lần lượt từ trên xuống; "
       "URL demo in ở bước 8. Model + index được cache, lần sau nhanh hơn.\n\n"
       "Thư mục dự án: `/content/drive/MyDrive/vilex-annd` (đồng bộ từ `G:\\My Drive\\vilex-annd` trên laptop)."),
    code(SETUP), code(INSTALL), code(LLM_CFG), code(INGEST), code(VLLM), code(VLLM_SMOKE), code(FRONTEND),
    code(API), code(TUNNEL), code(ACCEPT), md("## Tiện ích"), code(RESTART_API), code(LLAMACPP),
]
EVAL = [md(EVAL_INTRO), code(SETUP), code(INSTALL), code(LLM_CFG), code(EVAL_INDEX), code(VLLM), code(EVAL_DRAFT),
        code(EVAL_TAU), code(EVAL_RETR), code(EVAL_E2E), code(EVAL_FP8), code(EVAL_REPORT)]


def main() -> None:
    out = ROOT / "notebooks"
    out.mkdir(exist_ok=True)
    for name, cells in [("colab_serve.ipynb", SERVE), ("colab_eval.ipynb", EVAL)]:
        (out / name).write_text(json.dumps(notebook(cells), ensure_ascii=False, indent=1), encoding="utf-8")
        print("->", out / name)


if __name__ == "__main__":
    main()
