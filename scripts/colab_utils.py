"""Hàm tiện ích cho notebook Colab: chạy vLLM / API / tunnel nền, build frontend ngoài Drive."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

LOG_DIR = Path("/content/logs")


def sh(cmd: str, check: bool = True) -> str:
    print("$", cmd)
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    out = (r.stdout or "") + (r.stderr or "")
    if check and r.returncode != 0:
        raise RuntimeError(f"Lệnh lỗi ({r.returncode}):\n{out[-3000:]}")
    return out


def gpu_total_gb() -> float:
    try:
        out = subprocess.run("nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits",
                             shell=True, text=True, capture_output=True).stdout
        return float(out.strip().splitlines()[0]) / 1024
    except Exception:
        return 0.0


# Ngân sách VRAM cho vLLM tính theo GiB tuyệt đối (không theo tỷ lệ cố định), đo cho QuantTrio/Qwen3.6-35B-A3B-AWQ:
#   trọng số 23,7 GiB (25,5 GB — AWQ giữ FP16 cho visual, attention, linear_attn, shared_expert, layer 0, MTP)
#   + activation khi prefill 4096 token ~1,5–2 GiB + CUDA graph (≤16 chuỗi) ~0,5 GiB
#   + KV cache 10 lớp full-attention (20 KiB/token) + trạng thái 30 lớp Gated DeltaNet (~33 MiB/chuỗi) ~3 GiB
VLLM_BUDGET_GIB = 30.0
# Phần còn lại cho tiến trình API: bge-m3 + bge-reranker-v2-m3 FP16 (~2,2 GiB) + activation + CUDA context ≈ 4–5 GiB
API_RESERVE_GIB = 5.0
# Cờ vLLM giữ bộ nhớ trong ngân sách trên (mặc định vLLM: 256 chuỗi đồng thời, profiling cả tháp xử lý ảnh)
VLLM_LEAN_ARGS = ("--max-num-seqs 16 --max-num-batched-tokens 4096 "
                  "--limit-mm-per-prompt '{\"image\": 0, \"video\": 0}'")


def auto_gpu_util(total_gb: float | None = None, budget_gib: float = VLLM_BUDGET_GIB) -> float:
    """--gpu-memory-utilization = ngân sách vLLM / tổng VRAM. Cảnh báo nếu không còn chỗ cho embedding + reranker."""
    total = total_gb if total_gb is not None else gpu_total_gb()
    if total <= 0:
        return 0.85
    if total < budget_gib + API_RESERVE_GIB:
        print(f"⚠ GPU {total:.0f} GiB < {budget_gib + API_RESERVE_GIB:.0f} GiB cần cho LLM + embedding + reranker. "
              "Chọn một: đặt DEVICE=cpu cho embedding/reranker (chậm hơn), hoặc dùng llama.cpp GGUF (cell dự phòng).")
        return round(min(0.92, budget_gib / total), 2)
    return round(budget_gib / total, 2)


def _popen(cmd: list[str] | str, log_name: str, env: dict | None = None, cwd: str | None = None) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / log_name, "w")
    return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})},
                            cwd=cwd, shell=isinstance(cmd, str), start_new_session=True)


def tail(log_name: str, n: int = 40) -> str:
    p = LOG_DIR / log_name
    return "\n".join(p.read_text(errors="ignore").splitlines()[-n:]) if p.exists() else ""


def root_cause(log_name: str, n: int = 8) -> str:
    """Các dòng lỗi thật trong log (bỏ khung traceback), để không phải tự grep."""
    p = LOG_DIR / log_name
    if not p.exists():
        return ""
    lines = p.read_text(errors="ignore").splitlines()
    pat = re.compile(r"(\w+Error|Exception|out of memory|OutOfMemory|CUDA error|not supported|Unsupported)", re.I)
    hits = [ln for ln in lines if pat.search(ln) and 'File "' not in ln and not ln.strip().startswith(("~", "^"))]
    return "\n".join(hits[-n:])


def wait_http(url: str, timeout: int = 1200, proc: subprocess.Popen | None = None, log_name: str | None = None) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc is not None and proc.poll() is not None:
            print(tail(log_name or "", 15))
            print("\n=== NGUYÊN NHÂN (các dòng lỗi trong log) ===\n" + root_cause(log_name or ""))
            raise RuntimeError(f"Tiến trình đã dừng (exit {proc.returncode}) khi chờ {url}")
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    print(f"✓ {url} sẵn sàng sau {time.time() - t0:.0f}s")
                    return True
        except Exception:
            pass
        time.sleep(5)
    print(tail(log_name or "", 60))
    raise TimeoutError(f"Hết {timeout}s mà {url} chưa sẵn sàng")


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    import signal

    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        proc.wait(30)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def start_vllm(repo: str, served_name: str, port: int = 8000, max_len: int = 16384, gpu_util: float | None = None,
               hf_home: str = "/content/hf_cache", extra: str = "", lean: bool = True) -> subprocess.Popen:
    gpu_util = gpu_util or auto_gpu_util()
    cmd = (f"vllm serve {repo} --served-model-name {served_name} --port {port} --max-model-len {max_len} "
           f"--gpu-memory-utilization {gpu_util} --enable-prefix-caching {VLLM_LEAN_ARGS if lean else ''} {extra}")
    print("$", cmd)
    proc = _popen(cmd, "vllm.log", env={"HF_HOME": hf_home})
    wait_http(f"http://localhost:{port}/v1/models", timeout=1800, proc=proc, log_name="vllm.log")
    vram_report()
    return proc


def vram_report() -> None:
    """VRAM thật: vLLM tự báo trong log + từng tiến trình theo nvidia-smi. Dùng số này cho mục 'điều kiện, nguồn lực'."""
    p = LOG_DIR / "vllm.log"
    if p.exists():
        keys = ("Model loading took", "Available KV cache memory", "GPU KV cache size", "Maximum concurrency",
                "CUDA graph", "mamba", "Mamba", "gpu_memory_utilization")
        for ln in p.read_text(errors="ignore").splitlines():
            if any(k in ln for k in keys) and "Capturing" not in ln:
                print("  vLLM:", re.sub(r"^.*?\] ", "", ln)[:220])
    print(sh("nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv", check=False).strip())
    print(sh("nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv", check=False).strip())


def ensure_node(min_major: int = 18) -> None:
    v = sh("node -v", check=False).strip()
    m = re.match(r"v(\d+)", v)
    if m and int(m.group(1)) >= min_major:
        print("node", v)
        return
    sh("curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y -qq nodejs")
    print("node", sh("node -v").strip())


def build_frontend(project: str, force: bool = False) -> None:
    """Build ngoài Drive (node_modules trên Drive rất chậm), rồi chép dist về project/frontend/dist."""
    src = Path(project) / "frontend"
    dist = src / "dist"
    built = (dist / "index.html").stat().st_mtime if (dist / "index.html").exists() else 0
    newest = max(p.stat().st_mtime for p in [*(src / "src").rglob("*"), src / "package.json", src / "index.html"]
                 if p.is_file())
    if built >= newest and not force:
        print(f"{dist} đã mới nhất (force=True để build lại)")
        return
    ensure_node()
    work = Path("/content/fe_build")
    if work.exists():
        shutil.rmtree(work / "src", ignore_errors=True)
    shutil.copytree(src, work, dirs_exist_ok=True, ignore=shutil.ignore_patterns("node_modules", "dist"))
    sh(f"cd {work} && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund) && npm run build")
    if dist.exists():
        shutil.rmtree(dist)
    shutil.copytree(work / "dist", dist)
    lock = work / "package-lock.json"
    if lock.exists() and not (src / "package-lock.json").exists():
        shutil.copy(lock, src / "package-lock.json")  # lần sau npm ci nhanh và cố định phiên bản
    print("✓ frontend ->", dist)


def start_api(project: str, env: dict, port: int = 7860) -> subprocess.Popen:
    proc = _popen(f"python -m uvicorn api.main:app --host 0.0.0.0 --port {port}", "api.log", env=env, cwd=project)
    wait_http(f"http://localhost:{port}/api/health", timeout=900, proc=proc, log_name="api.log")
    return proc


def start_tunnel(port: int = 7860) -> tuple[subprocess.Popen, str]:
    """cloudflared quick tunnel: không cần tài khoản, URL *.trycloudflare.com đổi mỗi lần chạy."""
    binp = Path("/content/cloudflared")
    if not binp.exists():
        sh(f"wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O {binp}"
           f" && chmod +x {binp}")
    proc = _popen([str(binp), "tunnel", "--no-autoupdate", "--url", f"http://localhost:{port}"], "tunnel.log")
    for _ in range(60):
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", tail("tunnel.log", 200))
        if m:
            print("🌐 URL demo:", m.group(0))
            return proc, m.group(0)
        time.sleep(2)
    print(tail("tunnel.log"))
    raise TimeoutError("Không lấy được URL tunnel")


_TOKENS: dict[str, str] = {}


def login(role: str = "giang_vien", base: str = "http://localhost:7860") -> str:
    """Đăng nhập bằng tài khoản mặc định (auth.seed_users trong config.yaml) có vai trò `role`, trả về token."""
    import httpx

    from common.config import load_config

    if role not in _TOKENS:
        u = next(x for x in load_config().auth.seed_users if x.role == role)
        r = httpx.post(f"{base}/api/auth/login", json={"username": u.username, "password": u.password}, timeout=30)
        r.raise_for_status()
        _TOKENS[role] = r.json()["token"]
    return _TOKENS[role]


def ask(question: str, base: str = "http://localhost:7860", role: str = "giang_vien", mode: str = "answer") -> dict:
    """Gọi /api/chat (mỗi câu một hội thoại mới), gom các event SSE — để kiểm tra nhanh trong notebook."""
    import json

    import httpx

    events: dict = {"tokens": []}
    headers = {"Authorization": f"Bearer {login(role, base)}"}
    with httpx.stream("POST", f"{base}/api/chat", json={"question": question, "mode": mode}, headers=headers,
                      timeout=300) as r:
        name = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:") and name:
                data = json.loads(line[5:])
                if name == "token":
                    events["tokens"].append(data["delta"])
                else:
                    events[name] = data
    return events
