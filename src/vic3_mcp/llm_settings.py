"""OpenAI-compatible LLM settings (base URL / key / model)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vic3_mcp.paths import cache_dir

DEFAULT_BASE_URL = ""
DEFAULT_MODEL = "kimi-k3"
SETTINGS_FILE = "web-settings.json"


def _defaults() -> dict[str, Any]:
    return {
        "base_url": os.environ.get("VIC3_LLM_BASE_URL") or DEFAULT_BASE_URL,
        "api_key": os.environ.get("VIC3_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "",
        "model": os.environ.get("VIC3_LLM_MODEL") or DEFAULT_MODEL,
        "auto_refresh_sec": 20,
    }


def settings_path() -> Path:
    return cache_dir() / SETTINGS_FILE


def load_settings() -> dict[str, Any]:
    data = _defaults()
    path = settings_path()
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for k in ("base_url", "api_key", "model", "auto_refresh_sec"):
                    if saved.get(k) not in (None, ""):
                        data[k] = saved[k]
        except (OSError, json.JSONDecodeError):
            pass
    data["base_url"] = str(data["base_url"]).rstrip("/")
    try:
        data["auto_refresh_sec"] = max(5, min(300, int(data.get("auto_refresh_sec") or 20)))
    except (TypeError, ValueError):
        data["auto_refresh_sec"] = 20
    return data


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    if "base_url" in patch and patch["base_url"]:
        current["base_url"] = str(patch["base_url"]).strip().rstrip("/")
    if "api_key" in patch and str(patch["api_key"]).strip() and not str(patch["api_key"]).endswith("••••"):
        current["api_key"] = str(patch["api_key"]).strip()
    if "model" in patch and patch["model"]:
        current["model"] = str(patch["model"]).strip()
    if "auto_refresh_sec" in patch and patch["auto_refresh_sec"] is not None:
        current["auto_refresh_sec"] = max(5, min(300, int(patch["auto_refresh_sec"])))
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def public_settings() -> dict[str, Any]:
    s = load_settings()
    key = s.get("api_key") or ""
    masked = ""
    if key:
        masked = key[:3] + "••••" + key[-4:] if len(key) > 8 else "••••"
    return {
        "base_url": s["base_url"],
        "api_key_masked": masked,
        "api_key_set": bool(key),
        "model": s["model"],
        "auto_refresh_sec": s["auto_refresh_sec"],
        "default_model": DEFAULT_MODEL,
        "default_base_url": DEFAULT_BASE_URL,
    }
