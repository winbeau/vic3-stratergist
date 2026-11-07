"""Turn a .v3 save into melted Clausewitz text via rakaly."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from vic3_mcp.paths import cache_dir, rakaly_binary


def _fingerprint(save: Path) -> str:
    st = save.stat()
    raw = f"{save.resolve()}|{st.st_mtime_ns}|{st.st_size}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def is_probably_text(save: Path) -> bool:
    with save.open("rb") as f:
        head = f.read(64)
    if head.startswith(b"SAV") and b"PK\x03\x04" in head:
        return False
    if b"meta_data" in head or b"country_manager" in head:
        return True
    # Uncompressed text saves still start with SAV then plaintext
    if head.startswith(b"SAV") and b"{" in head:
        return True
    return False


def melt_save(save: Path, *, force: bool = False) -> Path:
    """Return a path to melted plaintext. Cached by source mtime/size."""
    save = save.expanduser().resolve()
    if not save.exists():
        raise FileNotFoundError(save)
    if is_probably_text(save) and save.stat().st_size > 1_000_000:
        return save

    dest = cache_dir() / f"{save.stem}_{_fingerprint(save)}.melted.v3"
    if dest.exists() and not force and dest.stat().st_mtime >= save.stat().st_mtime:
        return dest

    rakaly = rakaly_binary()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    cmd = [
        str(rakaly),
        "melt",
        "--format",
        "vic3",
        "-u",
        "stringify",
        "-o",
        str(tmp),
        str(save),
    ]
    env = os.environ.copy()
    proc = subprocess.run(cmd, capture_output=True, env=env)
    if proc.returncode not in (0, 1):
        # rakaly exits 1 when unknown tokens were stringified
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"rakaly melt failed ({proc.returncode}): {err[-2000:]}")
    if proc.returncode == 1 and not tmp.exists():
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"rakaly melt failed: {err[-2000:]}")
    if not tmp.exists():
        err = (proc.stderr or proc.stdout).decode("utf-8", errors="replace")
        raise RuntimeError(f"rakaly produced no output: {err[-2000:]}")
    tmp.replace(dest)
    return dest
