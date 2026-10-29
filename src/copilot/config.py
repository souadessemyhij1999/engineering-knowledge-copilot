from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _coerce(value: str, like: Any) -> Any:
    if isinstance(like, bool):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(like, int):
        return int(value)
    if isinstance(like, float):
        return float(value)
    return value


def load_settings(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Read settings.yaml, then apply COPILOT_<SECTION>_<KEY> env vars, then
    explicit overrides (used by tests)."""
    path = Path(path or os.environ.get("COPILOT_SETTINGS", ROOT / "configs" / "settings.yaml"))
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    for section, values in cfg.items():
        for key, val in values.items():
            env = os.environ.get(f"COPILOT_{section}_{key}".upper())
            if env is not None:
                values[key] = _coerce(env, val)
    # common shortcut names
    if os.environ.get("DATABASE_URL"):
        cfg["database"]["url"] = os.environ["DATABASE_URL"]
    for section, values in (overrides or {}).items():
        cfg.setdefault(section, {}).update(values)
    return cfg


def resolve(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


@lru_cache(maxsize=1)
def settings() -> dict:
    return load_settings()
