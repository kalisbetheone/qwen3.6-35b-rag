"""Tài khoản và đăng nhập.

- Mật khẩu băm PBKDF2-SHA256 (200k vòng, salt riêng) trong appdata/users.json — không lưu bản rõ.
- Token: payload JSON ký HMAC-SHA256 bằng khoá bí mật (appdata/secret.key, tự sinh lần đầu, hoặc VILEX_SECRET).
- Vai trò người dùng lấy từ token phía server; client không tự khai báo vai trò được.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from common.config import AppConfig

ITERATIONS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


@dataclass
class User:
    username: str
    role: str
    display_name: str

    def to_dict(self) -> dict:
        return {"username": self.username, "role": self.role, "display_name": self.display_name}


class UserStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._users: dict[str, dict] = {}
        if path.exists():
            self._users = json.loads(path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._users, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def ensure_seed(self, cfg: AppConfig) -> None:
        """Tạo tài khoản mặc định nếu chưa có; không ghi đè tài khoản đã tồn tại."""
        with self._lock:
            changed = False
            for u in cfg.auth.seed_users:
                if u.username not in self._users:
                    self._users[u.username] = {"role": u.role, "display_name": u.display_name or u.username,
                                               "password_hash": hash_password(u.password),
                                               "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                    changed = True
            if changed:
                self._save()

    def authenticate(self, username: str, password: str) -> User | None:
        rec = self._users.get(username.strip().lower())
        if rec is None:
            verify_password(password, hash_password("x"))  # cân thời gian, tránh dò tên tài khoản
            return None
        if not verify_password(password, rec["password_hash"]):
            return None
        return User(username.strip().lower(), rec["role"], rec.get("display_name", username))

    def get(self, username: str) -> User | None:
        rec = self._users.get(username)
        return User(username, rec["role"], rec.get("display_name", username)) if rec else None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class TokenSigner:
    def __init__(self, secret: bytes, ttl_hours: float):
        self.secret = secret
        self.ttl = ttl_hours * 3600

    @classmethod
    def from_config(cls, cfg: AppConfig) -> TokenSigner:
        env = os.environ.get("VILEX_SECRET")
        if env:
            secret = env.encode()
        else:
            p = cfg.app_path / "secret.key"
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(secrets.token_bytes(32))
            secret = p.read_bytes()
        return cls(secret, cfg.auth.token_ttl_hours)

    def issue(self, user: User) -> str:
        payload = _b64(json.dumps({"sub": user.username, "role": user.role,
                                   "exp": int(time.time() + self.ttl)}).encode())
        sig = _b64(hmac.new(self.secret, payload.encode(), hashlib.sha256).digest())
        return f"{payload}.{sig}"

    def verify(self, token: str) -> dict | None:
        try:
            payload, sig = token.split(".")
        except ValueError:
            return None
        good = _b64(hmac.new(self.secret, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        try:
            data = json.loads(_unb64(payload))
        except (ValueError, json.JSONDecodeError):
            return None
        return data if data.get("exp", 0) > time.time() else None
