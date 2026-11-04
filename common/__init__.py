"""Đặt trước khi bất kỳ thư viện nào khởi tạo GPU: không cho TensorFlow/JAX (cài sẵn trên Colab, bị kéo vào
gián tiếp qua thư viện phụ thuộc) giành phần VRAM còn trống của GPU dùng chung với vLLM. Hệ thống chỉ dùng PyTorch.
Mọi điểm vào (build_index, API, eval) đều import `common` trước torch/transformers/bm25s."""
import os

for _k, _v in {
    "JAX_PLATFORMS": "cpu",                 # JAX không chạm GPU
    "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
    "TF_FORCE_GPU_ALLOW_GROWTH": "true",    # TensorFlow không chiếm trước toàn bộ VRAM
    "TF_CPP_MIN_LOG_LEVEL": "2",
    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
}.items():
    os.environ.setdefault(_k, _v)
