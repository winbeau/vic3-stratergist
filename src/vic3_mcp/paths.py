"""Locate Victoria 3 saves, game files, rakaly, and local caches."""

from __future__ import annotations

import os
import platform
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
VENDOR_RAKALY = PACKAGE_ROOT / "vendor" / "rakaly"


def home() -> Path:
    return Path.home()


def documents_dir() -> Path:
    return home() / "Documents"


def vic3_user_dir() -> Path:
    override = os.environ.get("VIC3_USER_DIR")
    if override:
        return Path(override).expanduser()
    system = platform.system()
    if system == "Darwin":
        return documents_dir() / "Paradox Interactive" / "Victoria 3"
    if system == "Windows":
        return documents_dir() / "Paradox Interactive" / "Victoria 3"
    # Linux
    return home() / ".local" / "share" / "Paradox Interactive" / "Victoria 3"


def save_dir() -> Path:
    override = os.environ.get("VIC3_SAVE_DIR")
    if override:
        return Path(override).expanduser()
    return vic3_user_dir() / "save games"


def cache_dir() -> Path:
    override = os.environ.get("VIC3_MCP_CACHE")
    if override:
        return Path(override).expanduser()
    system = platform.system()
    if system == "Darwin":
        base = home() / "Library" / "Caches" / "vic3-mcp"
    elif system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", home() / "AppData" / "Local")) / "vic3-mcp"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", home() / ".cache")) / "vic3-mcp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def steam_vic3_dir() -> Path | None:
    override = os.environ.get("VIC3_GAME_DIR")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None
    candidates: list[Path] = []
    system = platform.system()
    if system == "Darwin":
        candidates.append(
            home()
            / "Library"
            / "Application Support"
            / "Steam"
            / "steamapps"
            / "common"
            / "Victoria 3"
        )
    elif system == "Windows":
        for root in (
            Path(r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3"),
            Path(r"C:\Program Files\Steam\steamapps\common\Victoria 3"),
        ):
            candidates.append(root)
    else:
        candidates.extend(
            [
                home() / ".steam" / "steam" / "steamapps" / "common" / "Victoria 3",
                home() / ".local" / "share" / "Steam" / "steamapps" / "common" / "Victoria 3",
            ]
        )
    for c in candidates:
        if c.exists():
            return c
    return None


def game_data_dir() -> Path | None:
    root = steam_vic3_dir()
    if root is None:
        return None
    game = root / "game"
    return game if game.exists() else None


def rakaly_binary() -> Path:
    override = os.environ.get("RAKALY")
    if override:
        return Path(override).expanduser()
    if VENDOR_RAKALY.exists():
        return VENDOR_RAKALY
    from shutil import which

    found = which("rakaly")
    if found:
        return Path(found)
    raise FileNotFoundError(
        "rakaly not found. Place the binary at vendor/rakaly or set RAKALY=."
    )
