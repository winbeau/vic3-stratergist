"""Load Victoria 3 localization and small definition tables from the install."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from vic3_mcp.paths import game_data_dir

LOC_RE = re.compile(
    r'^\s*([A-Za-z0-9_.\-]+):(?:\d+)?\s+"(.*)"\s*$'
)

POP_TYPES = [
    "academics",
    "aristocrats",
    "bureaucrats",
    "capitalists",
    "clergymen",
    "clerks",
    "engineers",
    "farmers",
    "laborers",
    "machinists",
    "officers",
    "peasants",
    "shopkeepers",
    "slaves",
    "soldiers",
]

STRATA = {0: "lower", 1: "middle", 2: "upper"}

# Vic3 1.13 weekly budget arrays (best-effort; named building budget is authoritative).
INCOME_LABELS = [
    "unused_0",
    "unused_1",
    "minting",
    "income_taxes",
    "poll_taxes",
    "tariffs",
    "diplomatic_pacts",
    "interest",
    "additional_income",
    "investment_transfers",
    "port_tariffs",
    "tolls",
    "company_dividends",
    "unused_13",
    "unused_14",
    "other",
]
EXPENSE_LABELS = [
    "unused_0",
    "unused_1",
    "government_goods",
    "government_wages",
    "unused_4",
    "military_goods",
    "military_wages",
    "unused_7",
    "subsidies",
    "unused_9",
    "unused_10",
    "unused_11",
    "unused_12",
    "unused_13",
    "government_share_losses",
    "unused_15",
    "interest",
    "diplomatic_pacts",
    "unused_18",
    "construction",
    "unused_20",
    "other",
]


def _unescape_loc(s: str) -> str:
    return s.replace(r"\"", '"').replace(r"\\", "\\")


def _iter_yml(folder: Path) -> Iterable[Path]:
    if not folder.exists():
        return []
    return folder.rglob("*.yml")


def load_localization(lang: str = "simp_chinese") -> dict[str, str]:
    """Load Paradox loc keys. `lang` is the folder name under localization/."""
    root = game_data_dir()
    if root is None:
        return {}
    loc_root = root / "localization"
    files: list[Path] = []
    preferred = loc_root / lang
    english = loc_root / "english"
    if preferred.exists():
        files.extend(_iter_yml(preferred))
    if english.exists() and preferred.resolve() != english.resolve():
        files.extend(_iter_yml(english))
    # english first, then preferred overwrites
    files = list(_iter_yml(english)) + list(_iter_yml(preferred))
    table: dict[str, str] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = LOC_RE.match(line)
            if not m:
                continue
            table[m.group(1)] = _unescape_loc(m.group(2))
    return table


@lru_cache(maxsize=2)
def localization(lang: str = "simp_chinese") -> dict[str, str]:
    return load_localization(lang)


def loc(key: str | None, lang: str = "simp_chinese", default: str | None = None) -> str:
    if not key:
        return default or ""
    table = localization(lang)
    if key in table:
        return table[key]
    # Common Vic3 prefixes
    for candidate in (
        key,
        f"{key}_desc",
        key.removeprefix("law_"),
    ):
        if candidate in table:
            return table[candidate]
    return default if default is not None else key


def loc_many(keys: Iterable[str], lang: str = "simp_chinese") -> dict[str, str]:
    return {k: loc(k, lang) for k in keys}


def pop_type_name(index: int, lang: str = "simp_chinese") -> str:
    if 0 <= index < len(POP_TYPES):
        ident = POP_TYPES[index]
        return loc(ident, lang, ident)
    return f"pop_type_{index}"
