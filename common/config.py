"""Đọc config.yaml, ghi đè bằng biến môi trường, trả về object có kiểu."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]


class PathsCfg(BaseModel):
    raw_dir: str = "data/raw"
    registry: str = "data/registry.csv"
    chunks: str = "data/processed/chunks.jsonl"
    articles: str = "data/processed/articles.jsonl"
    index_dir: str = "index"
    log_dir: str = "logs"
    prompts_dir: str = "prompts"
    frontend_dist: str = "frontend/dist"
    app_dir: str = "appdata"


class ChunkingCfg(BaseModel):
    min_article_tokens: int = 300
    max_clause_tokens: int = 700
    max_intro_tokens: int = 120
    tokenizer: str = "heuristic"


class RetrievalCfg(BaseModel):
    use_router: bool = True
    use_bm25: bool = True
    use_dense: bool = True
    use_rerank: bool = True
    bm25_tokenizer: str = "underthesea"
    bm25_top_k: int = 30
    dense_top_k: int = 30
    rrf_k: int = 60
    fusion_top_k: int = 20
    top_k: int = 5
    rerank_threshold: float = 0.30
    expired_penalty: float = 0.85
    parent_expansion: bool = True
    parent_max_tokens: int = 1500
    router_default_doc_id: str | None = None


class ModelsCfg(BaseModel):
    embed_model: str = "BAAI/bge-m3"
    embed_query_prefix: str = ""
    embed_passage_prefix: str = ""
    embed_word_segment: bool = False
    embed_max_length: int = 1024
    embed_batch_size: int = 32
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_max_length: int = 1024
    rerank_batch_size: int = 20
    device: str = "cuda"
    fp16: bool = True


class LLMCfg(BaseModel):
    provider: str = "openai"
    base_url: str = "http://localhost:8000/v1"
    model: str = "qwen3.6-35b-a3b"
    api_key: str = "EMPTY"
    temperature: float = 0.15
    max_tokens: int = 800
    enable_thinking: bool = False
    timeout: float = 180
    max_history_turns: int = 6


class VerifyCfg(BaseModel):
    weak_threshold: float = 0.20


class ApiCfg(BaseModel):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class SeedUser(BaseModel):
    username: str
    password: str
    role: str
    display_name: str = ""


class AuthCfg(BaseModel):
    token_ttl_hours: float = 12
    seed_users: list[SeedUser] = Field(default_factory=list)


class UploadCfg(BaseModel):
    allowed_roles: list[str] = Field(default_factory=lambda: ["giang_vien"])
    max_mb: float = 30
    extensions: list[str] = Field(default_factory=lambda: [".docx", ".pdf", ".txt", ".md"])


class AppConfig(BaseModel):
    paths: PathsCfg = Field(default_factory=PathsCfg)
    chunking: ChunkingCfg = Field(default_factory=ChunkingCfg)
    retrieval: RetrievalCfg = Field(default_factory=RetrievalCfg)
    models: ModelsCfg = Field(default_factory=ModelsCfg)
    llm: LLMCfg = Field(default_factory=LLMCfg)
    verify: VerifyCfg = Field(default_factory=VerifyCfg)
    api: ApiCfg = Field(default_factory=ApiCfg)
    auth: AuthCfg = Field(default_factory=AuthCfg)
    upload: UploadCfg = Field(default_factory=UploadCfg)
    roles: dict[str, list[str]] = Field(
        default_factory=lambda: {"hoc_vien": ["public"], "giang_vien": ["public", "internal"]}
    )
    suggested_questions: list[str] = Field(default_factory=list)

    def path(self, rel: str) -> Path:
        """Đường dẫn tương đối trong config -> tuyệt đối theo gốc repo."""
        p = Path(rel)
        return p if p.is_absolute() else ROOT / p

    @property
    def app_path(self) -> Path:
        return self.path(self.paths.app_dir)

    @property
    def uploads_raw_dir(self) -> Path:
        return self.app_path / "uploads" / "raw"

    @property
    def uploads_registry(self) -> Path:
        return self.app_path / "uploads" / "registry.csv"

    @property
    def index_path(self) -> Path:
        """index/<tên embed model đã làm sạch>/"""
        return self.path(self.paths.index_dir) / model_slug(self.models.embed_model)

    def allowed_levels(self, role: str) -> list[str]:
        return self.roles.get(role, ["public"])


def model_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.split("/")[-1])


def _to_bool(v: str) -> bool:
    return v.strip().lower() in {"1", "true", "yes", "on"}


_ENV = {
    "EMBED_MODEL": ("models", "embed_model", str),
    "RERANK_MODEL": ("models", "rerank_model", str),
    "DEVICE": ("models", "device", str),
    "LLM_BASE_URL": ("llm", "base_url", str),
    "LLM_MODEL": ("llm", "model", str),
    "LLM_PROVIDER": ("llm", "provider", str),
    "INDEX_DIR": ("paths", "index_dir", str),
    "RERANK_THRESHOLD": ("retrieval", "rerank_threshold", float),
    "TOP_K": ("retrieval", "top_k", int),
    "USE_DENSE": ("retrieval", "use_dense", _to_bool),
    "USE_RERANK": ("retrieval", "use_rerank", _to_bool),
}


# Thiết lập riêng theo model embedding, tự áp khi đổi model (vẫn ghi đè được bằng overrides).
# DEk21: RoBERTa/PhoBERT, max_position_embeddings = 258 -> tối đa 256 token (đặt cao hơn sẽ lỗi
# "index out of bounds" trên GPU); input cần tách từ (pyvi) như PhoBERT.
MODEL_PRESETS = {
    "huyydangg/DEk21_hcmute_embedding": {"embed_word_segment": True, "embed_max_length": 256},
}


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> AppConfig:
    """path > $VILEX_CONFIG > config.yaml ở gốc repo. overrides: {"retrieval.top_k": 3, ...}.
    Thứ tự ưu tiên: overrides > biến môi trường > preset theo model > file yaml."""
    path = Path(path or os.environ.get("VILEX_CONFIG") or ROOT / "config.yaml")
    raw: dict = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    embed = ((overrides or {}).get("models.embed_model") or os.environ.get("EMBED_MODEL")
             or raw.get("models", {}).get("embed_model"))
    raw.setdefault("models", {}).update(MODEL_PRESETS.get(embed, {}))
    for env, (section, key, cast) in _ENV.items():
        if os.environ.get(env):
            raw.setdefault(section, {})[key] = cast(os.environ[env])
    for dotted, value in (overrides or {}).items():
        section, key = dotted.split(".", 1)
        raw.setdefault(section, {})[key] = value
    return AppConfig.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
