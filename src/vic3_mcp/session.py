"""Loaded-save session: melt, index, and lazy extracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vic3_mcp.analyze import analyze_country
from vic3_mcp.clausewitz import index_top_level
from vic3_mcp.extract import (
    build_country_map,
    culture_lookup,
    extract_buildings,
    extract_characters,
    extract_country,
    extract_diplomacy,
    extract_institutions,
    extract_interest_groups,
    extract_journal,
    extract_laws,
    extract_meta,
    extract_military,
    extract_rankings,
    extract_states,
    extract_technology,
    resolve_cultures,
)
from vic3_mcp.gamedata import loc
from vic3_mcp.melt import melt_save
from vic3_mcp.paths import save_dir, vic3_user_dir


def list_save_files() -> list[dict[str, Any]]:
    folder = save_dir()
    if not folder.exists():
        return []
    rows = []
    for p in sorted(folder.glob("*.v3"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        rows.append(
            {
                "name": p.stem,
                "filename": p.name,
                "path": str(p),
                "size_mb": round(st.st_size / 1_048_576, 2),
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "autosave": p.stem.startswith("autosave"),
            }
        )
    return rows


def continue_save_hint() -> str | None:
    p = vic3_user_dir() / "continue_game.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data.get("title")


@dataclass
class Vic3Session:
    save_path: Path
    melted_path: Path
    lang: str = "simp_chinese"
    index: dict[str, tuple[int, int]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    country_map: dict[int, dict[str, Any]] = field(default_factory=dict)
    tag_to_id: dict[str, int] = field(default_factory=dict)
    player_id: int | None = None
    _cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        save: str | Path,
        *,
        lang: str = "simp_chinese",
        force_melt: bool = False,
        progress: Any | None = None,
    ) -> "Vic3Session":
        def p(pct: int, label: str) -> None:
            if progress:
                progress(pct, label)

        path = Path(save).expanduser()
        if not path.exists():
            # Treat as stem in the save folder
            candidate = save_dir() / f"{save}.v3"
            if not candidate.exists():
                candidate = save_dir() / str(save)
            if not candidate.exists():
                raise FileNotFoundError(f"save not found: {save}")
            path = candidate
        p(8, "融化二进制存档")
        melted = melt_save(path, force=force_melt)
        p(22, "索引存档结构")
        index = index_top_level(melted)
        sess = cls(save_path=path, melted_path=melted, lang=lang, index=index)
        p(30, "读取元数据")
        sess.meta = extract_meta(melted, index)
        p(36, "扫描各国摘要")
        sess.country_map = build_country_map(melted, index)
        sess.tag_to_id = {row["tag"]: cid for cid, row in sess.country_map.items() if row.get("tag")}
        sess.player_id = sess.meta.get("player_country_id")
        if sess.player_id not in sess.country_map:
            # fall back to CHI / highest GDP
            if "CHI" in sess.tag_to_id:
                sess.player_id = sess.tag_to_id["CHI"]
            elif sess.country_map:
                sess.player_id = max(sess.country_map, key=lambda i: sess.country_map[i].get("gdp") or 0)
        p(55, "定位玩家国家")
        return sess

    def resolve_country(self, tag_or_id: str | int | None = None) -> int:
        if tag_or_id is None or tag_or_id == "" or tag_or_id == "player":
            if self.player_id is None:
                raise KeyError("no player country")
            return self.player_id
        if isinstance(tag_or_id, int) or (isinstance(tag_or_id, str) and tag_or_id.isdigit()):
            cid = int(tag_or_id)
            if cid not in self.country_map:
                raise KeyError(f"unknown country id {cid}")
            return cid
        tag = str(tag_or_id).upper()
        if tag in self.tag_to_id:
            return self.tag_to_id[tag]
        # try loc name match
        needle = str(tag_or_id)
        for cid, row in self.country_map.items():
            name = loc(row.get("dynamic_name"), self.lang, None) or loc(row.get("tag"), self.lang, "")
            if needle in {row.get("tag"), name, row.get("dynamic_name")}:
                return cid
        raise KeyError(f"unknown country {tag_or_id}")

    def country(self, tag_or_id: str | int | None = None) -> dict[str, Any]:
        cid = self.resolve_country(tag_or_id)
        key = f"country:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_country(self.melted_path, self.index, cid, lang=self.lang)
        return self._cache[key]

    def rankings(self) -> list[dict[str, Any]]:
        if "rankings" not in self._cache:
            self._cache["rankings"] = extract_rankings(
                self.melted_path, self.index, self.country_map, self.lang
            )
        return self._cache["rankings"]

    def interest_groups(self, tag_or_id: str | int | None = None) -> list[dict[str, Any]]:
        cid = self.resolve_country(tag_or_id)
        key = f"ig:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_interest_groups(self.melted_path, self.index, cid, self.lang)
        return self._cache[key]

    def laws(self, tag_or_id: str | int | None = None) -> list[dict[str, Any]]:
        cid = self.resolve_country(tag_or_id)
        key = f"laws:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_laws(self.melted_path, self.index, cid, self.lang)
        return self._cache[key]

    def institutions(self, tag_or_id: str | int | None = None) -> list[dict[str, Any]]:
        cid = self.resolve_country(tag_or_id)
        key = f"inst:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_institutions(self.melted_path, self.index, cid, self.lang)
        return self._cache[key]

    def technology(self, tag_or_id: str | int | None = None) -> dict[str, Any]:
        cid = self.resolve_country(tag_or_id)
        key = f"tech:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_technology(self.melted_path, self.index, cid, self.lang)
        return self._cache[key]

    def journal(self, tag_or_id: str | int | None = None) -> list[dict[str, Any]]:
        cid = self.resolve_country(tag_or_id)
        key = f"je:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_journal(self.melted_path, self.index, cid, self.lang)
        return self._cache[key]

    def diplomacy(self, tag_or_id: str | int | None = None) -> dict[str, Any]:
        cid = self.resolve_country(tag_or_id)
        key = f"dip:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_diplomacy(
                self.melted_path, self.index, cid, self.country_map, self.lang
            )
        return self._cache[key]

    def military(self, tag_or_id: str | int | None = None) -> dict[str, Any]:
        cid = self.resolve_country(tag_or_id)
        key = f"mil:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_military(self.melted_path, self.index, cid)
        return self._cache[key]

    def characters(self, tag_or_id: str | int | None = None) -> list[dict[str, Any]]:
        c = self.country(tag_or_id)
        ids = [c.get("ruler_id"), c.get("heir_id")]
        for ig in self.interest_groups(tag_or_id):
            ids.append(ig.get("leader_id"))
        cid = self.resolve_country(tag_or_id)
        key = f"char:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_characters(
                self.melted_path, self.index, [i for i in ids if i is not None], cid, self.lang
            )
        return self._cache[key]

    def states(self, tag_or_id: str | int | None = None) -> list[dict[str, Any]]:
        c = self.country(tag_or_id)
        cid = c["id"]
        key = f"states:{cid}"
        if key not in self._cache:
            self._cache[key] = extract_states(
                self.melted_path, self.index, set(c.get("state_ids") or []), self.lang
            )
        return self._cache[key]

    def buildings(self, tag_or_id: str | int | None = None, top_n: int = 40) -> dict[str, Any]:
        c = self.country(tag_or_id)
        cid = c["id"]
        key = f"bld:{cid}:{top_n}"
        if key not in self._cache:
            self._cache[key] = extract_buildings(
                self.melted_path, self.index, set(c.get("state_ids") or []), self.lang, top_n=top_n
            )
        return self._cache[key]

    def cultures_resolved(self, tag_or_id: str | int | None = None) -> list[dict[str, Any]]:
        if "cultures_lookup" not in self._cache:
            self._cache["cultures_lookup"] = culture_lookup(self.melted_path, self.index)
        c = self.country(tag_or_id)
        return resolve_cultures(c.get("population", {}).get("by_culture_id") or {}, self._cache["cultures_lookup"], self.lang)

    def overview(self, tag_or_id: str | int | None = None) -> dict[str, Any]:
        c = self.country(tag_or_id)
        ranks = self.rankings()
        mine = next((r for r in ranks if r.get("country_id") == c["id"]), None)
        return {
            "save": self.save_path.name,
            "meta": self.meta,
            "country": {
                "id": c["id"],
                "tag": c["tag"],
                "name": c["name"],
                "government": c.get("government_name") or c.get("government"),
                "country_type": c.get("country_type"),
                "rank": (mine or {}).get("rank") or self.meta.get("rank"),
                "prestige_rank_score": (mine or {}).get("score"),
                "gdp": c.get("gdp"),
                "prestige": c.get("prestige"),
                "sol": c.get("sol"),
                "literacy": c.get("literacy"),
                "infamy": c.get("infamy"),
                "tax_level": c.get("tax_level"),
                "population": c.get("population", {}).get("total"),
                "states": c.get("num_states"),
                "treasury": c.get("treasury"),
            },
            "great_powers": [r for r in ranks if r.get("rank") == "great_power"][:10],
        }

    def politics(self, tag_or_id: str | int | None = None) -> dict[str, Any]:
        c = self.country(tag_or_id)
        return {
            "tag": c["tag"],
            "name": c["name"],
            "government": c.get("government_name"),
            "interest_groups": self.interest_groups(tag_or_id),
            "laws": self.laws(tag_or_id),
            "institutions": self.institutions(tag_or_id),
            "characters": self.characters(tag_or_id),
        }

    def analysis(self, tag_or_id: str | int | None = None) -> dict[str, Any]:
        c = self.country(tag_or_id)
        return analyze_country(
            meta=self.meta,
            country=c,
            igs=self.interest_groups(tag_or_id),
            laws=self.laws(tag_or_id),
            tech=self.technology(tag_or_id),
            journal=self.journal(tag_or_id),
            diplomacy=self.diplomacy(tag_or_id),
            military=self.military(tag_or_id),
            buildings=self.buildings(tag_or_id),
            rankings=self.rankings(),
        )

    def compare(self, tags: list[str]) -> list[dict[str, Any]]:
        rows = []
        ranks = {r.get("tag"): r for r in self.rankings()}
        for t in tags:
            try:
                c = self.country(t)
            except KeyError:
                rows.append({"tag": t, "error": "not found"})
                continue
            r = ranks.get(c["tag"], {})
            rows.append(
                {
                    "tag": c["tag"],
                    "name": c["name"],
                    "country_type": c.get("country_type"),
                    "rank": r.get("rank"),
                    "score": r.get("score"),
                    "gdp": c.get("gdp"),
                    "prestige": c.get("prestige") if c.get("prestige") is not None else r.get("prestige"),
                    "sol": c.get("sol"),
                    "literacy": c.get("literacy"),
                    "population": c.get("population", {}).get("total"),
                    "money": (c.get("treasury") or {}).get("money"),
                    "infamy": c.get("infamy"),
                    "tech_count": self.technology(t).get("count"),
                }
            )
        return rows

    def search_melted(self, needle: str, *, max_hits: int = 30) -> list[dict[str, Any]]:
        needle = needle.strip()
        if len(needle) < 2:
            raise ValueError("search string too short")
        hits = []
        with self.melted_path.open("r", encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                if needle in line:
                    hits.append({"line": lineno, "text": line.strip()[:240]})
                    if len(hits) >= max_hits:
                        break
        return hits
