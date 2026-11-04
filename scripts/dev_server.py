"""Chạy API trên laptop không cần GPU: BM25 + LLM 'echo' (trích câu đầu của nguồn), phục vụ luôn frontend/dist.

    python scripts/dev_server.py [--port 7860]
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7860)
    args = ap.parse_args()
    os.environ.setdefault("USE_DENSE", "false")
    os.environ.setdefault("USE_RERANK", "false")
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    import uvicorn

    uvicorn.run("api.main:app", host="127.0.0.1", port=args.port)
