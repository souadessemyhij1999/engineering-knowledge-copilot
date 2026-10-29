"""Users, roles, login tokens and document access rules."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

import jwt
import yaml


@dataclass(frozen=True)
class User:
    username: str
    full_name: str
    role: str


class AccessPolicy:
    def __init__(self, access_file: Path, users_file: Path, manifest: Path | None = None):
        cfg = yaml.safe_load(Path(access_file).read_text(encoding="utf-8"))
        self.roles: dict[str, str] = cfg["roles"]
        self.superuser_roles = set(cfg.get("superuser_roles", []))
        self.default_by_class: dict[str, list[str]] = cfg["default_roles_by_classification"]
        ucfg = yaml.safe_load(Path(users_file).read_text(encoding="utf-8"))
        self.users = {u["username"]: User(u["username"], u["full_name"], u["role"]) for u in ucfg["users"]}
        self._pw = {u: self._hash(ucfg.get("demo_password", "demo"), u) for u in self.users}
        self.acl: dict[tuple[str, str], list[str]] = {}
        if manifest and Path(manifest).exists():
            for row in json.loads(Path(manifest).read_text(encoding="utf-8")):
                self.acl[(row["doc_no"], str(row["revision"]))] = list(row["roles"])

    @staticmethod
    def _hash(password: str, salt: str) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)

    def authenticate(self, username: str, password: str) -> User | None:
        if username not in self.users:
            return None
        if not hmac.compare_digest(self._pw[username], self._hash(password, username)):
            return None
        return self.users[username]

    def roles_for_document(self, doc_no: str, revision: str, classification: str) -> list[str]:
        """Roles stored on every chunk. Superuser roles are always added."""
        roles = self.acl.get((doc_no, str(revision)))
        if roles is None:
            roles = self.default_by_class.get(classification, [])
        return sorted(set(roles) | self.superuser_roles)

    def search_roles(self, user: User) -> list[str]:
        """Roles used in the store filter."""
        return [user.role]

    def can_see(self, user: User, chunk_roles: list[str]) -> bool:
        return user.role in chunk_roles

    # ---- tokens -----------------------------------------------------------
    @staticmethod
    def issue_token(user: User, secret: str, minutes: int = 480) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        return jwt.encode({"sub": user.username, "role": user.role, "iat": now,
                           "exp": now + dt.timedelta(minutes=minutes)}, secret, algorithm="HS256")

    def user_from_token(self, token: str, secret: str) -> User | None:
        try:
            data = jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None
        return self.users.get(data.get("sub"))
