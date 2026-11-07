"""Live save hub: load, cache dashboard, seed and hold the advice board."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from vic3_mcp.analyze import analyze_country
from vic3_mcp.paths import save_dir
from vic3_mcp.session import Vic3Session, continue_save_hint, list_save_files

FLAG_TO_ACTION = {
    "unrecognized": ("diplomacy", "now", "争取列强承认"),
    "canton_system": ("diplomacy", "now", "应对一口通商 / 鸦片风险"),
    "isolationism": ("diplomacy", "now", "打开贸易或备战闭关代价"),
    "traditionalism": ("economy", "year", "改经济法：传统主义 → 农本"),
    "serfdom": ("society", "year", "择机废除农奴制"),
    "peasant_levies": ("military", "year", "军队职业化"),
    "low_sol": ("society", "now", "拉高生活水平、压激进派"),
    "literacy": ("tech", "year", "提高识字率"),
    "no_schools": ("tech", "year", "设立学校机构"),
    "landowner_power": ("politics", "now", "削弱乡绅/地主垄断"),
    "angry_igs": ("politics", "now", "安抚反对利益集团"),
    "warlord_china": ("politics", "now", "维持脆弱的统一"),
    "opium": ("military", "now", "鸦片战争备战"),
    "taiping": ("politics", "now", "处理内乱"),
    "unemployment": ("economy", "year", "消化失业劳动力"),
    "unprofitable_buildings": ("economy", "now", "处理亏损建筑"),
    "peasant_society": ("economy", "mid", "农民社会工业化"),
    "closed_borders": ("society", "mid", "边境与移民政策"),
    "debt": ("economy", "now", "控制国债"),
    "gold_drain": ("economy", "now", "扭转金库流失"),
    "over_saving": ("economy", "now", "把金库变成建筑"),
    "illegitimate": ("politics", "now", "拉高合法性"),
    "no_navy": ("military", "year", "组建舰队"),
}

PRIORITY_LABEL = {"now": "立刻", "year": "这一年", "mid": "中期"}
DIR_LABEL = {
    "politics": "政治",
    "economy": "经济",
    "military": "军事",
    "diplomacy": "外交",
    "tech": "科技",
    "society": "社会",
}


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _resolve_save(name: str | None) -> Path:
    if name:
        p = Path(name).expanduser()
        if p.exists():
            return p
        cand = save_dir() / f"{name}.v3"
        if cand.exists():
            return cand
        cand = save_dir() / name
        if cand.exists():
            return cand
        raise FileNotFoundError(name)
    hint = continue_save_hint() or "Qing_MCP"
    return _resolve_save(hint)


class SaveHub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.save_name = continue_save_hint() or "Qing_MCP"
        self.session: Vic3Session | None = None
        self.save_mtime: float = 0.0
        self.loaded_at: str | None = None
        self.dashboard: dict[str, Any] | None = None
        self.board: dict[str, Any] = {
            "intent": "",
            "source": "heuristic",
            "updated_at": None,
            "save_changed": False,
            "actions": [],
        }
        self.progress: dict[str, Any] = {"active": False, "pct": 0, "label": ""}

    def _set_progress(self, pct: int, label: str, *, active: bool = True) -> None:
        self.progress = {
            "active": active,
            "pct": max(0, min(100, int(pct))),
            "label": label,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            path = None
            try:
                path = _resolve_save(self.save_name)
            except FileNotFoundError:
                path = None
            disk_mtime = _mtime(path) if path else 0.0
            return {
                "save_name": self.save_name,
                "save_path": str(path) if path else None,
                "loaded": self.session is not None,
                "loaded_at": self.loaded_at,
                "disk_mtime": disk_mtime,
                "loaded_mtime": self.save_mtime,
                "stale": bool(self.session) and disk_mtime > self.save_mtime + 0.01,
                "saves": list_save_files(),
                "progress": dict(self.progress),
            }

    def refresh(
        self,
        save: str | None = None,
        *,
        force: bool = False,
        on_progress: Any | None = None,
    ) -> dict[str, Any]:
        def prog(pct: int, label: str, *, active: bool = True) -> None:
            self._set_progress(pct, label, active=active)
            if on_progress:
                on_progress(pct, label)

        with self._lock:
            if save:
                self.save_name = save
            prog(3, "定位存档")
            path = _resolve_save(self.save_name)
            mtime = _mtime(path)
            changed = self.session is None or force or mtime > self.save_mtime + 0.01
            if not changed and self.dashboard is not None:
                prog(100, "已是最新", active=False)
                return {
                    "reloaded": False,
                    "stale": False,
                    "dashboard": self.dashboard,
                    "board": self.board,
                }
            old_source = self.board.get("source")
            self.session = Vic3Session.load(path, progress=prog)
            self.save_mtime = mtime
            self.loaded_at = datetime.now().isoformat(timespec="seconds")
            self.dashboard = self._build_dashboard(progress=prog)
            if old_source != "agent" or not self.board.get("actions"):
                prog(97, "生成建议动作")
                self.board = {
                    "intent": self.board.get("intent") or "",
                    "source": "heuristic",
                    "updated_at": self.loaded_at,
                    "save_changed": False,
                    "actions": self._seed_actions(self.dashboard.get("analysis") or {}),
                }
            else:
                self.board["save_changed"] = True
            prog(100, "完成", active=False)
            return {
                "reloaded": True,
                "stale": False,
                "dashboard": self.dashboard,
                "board": self.board,
            }

    def set_board(self, *, intent: str | None = None, actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        with self._lock:
            if intent is not None:
                self.board["intent"] = intent
            if actions is not None:
                cleaned = []
                for i, raw in enumerate(actions):
                    if not isinstance(raw, dict):
                        continue
                    direction = str(raw.get("direction") or "politics")
                    if direction not in DIR_LABEL:
                        direction = "politics"
                    priority = str(raw.get("priority") or "year")
                    if priority not in PRIORITY_LABEL:
                        priority = "year"
                    title = str(raw.get("title") or "").strip()
                    if not title:
                        continue
                    cleaned.append(
                        {
                            "id": str(raw.get("id") or f"agent-{i}"),
                            "direction": direction,
                            "direction_label": DIR_LABEL[direction],
                            "priority": priority,
                            "priority_label": PRIORITY_LABEL[priority],
                            "title": title,
                            "detail": str(raw.get("detail") or "").strip(),
                            "reason": str(raw.get("reason") or "").strip(),
                            "source": "agent",
                        }
                    )
                self.board["actions"] = cleaned
                self.board["source"] = "agent"
            self.board["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self.board["save_changed"] = False
            return self.board

    def _build_dashboard(self, progress: Any | None = None) -> dict[str, Any]:
        assert self.session is not None
        s = self.session

        def p(pct: int, label: str) -> None:
            if progress:
                progress(pct, label)

        p(58, "读取国家总览")
        overview = s.overview()
        p(64, "读取利益集团")
        igs_raw = s.interest_groups()
        p(70, "读取法案")
        laws_raw = s.laws()
        p(74, "读取科技")
        tech = s.technology()
        p(78, "读取日志")
        journal = s.journal()
        p(82, "读取外交与军事")
        diplomacy = s.diplomacy()
        military = s.military()
        p(88, "汇总建筑")
        buildings = s.buildings()
        p(93, "生成局势分析")
        country = s.country()
        analysis = analyze_country(
            meta=s.meta,
            country=country,
            igs=igs_raw,
            laws=laws_raw,
            tech=tech,
            journal=journal,
            diplomacy=diplomacy,
            military=military,
            buildings=buildings,
            rankings=s.rankings(),
        )
        igs = [
            {
                "definition": g.get("definition"),
                "name": g.get("name"),
                "clout": g.get("clout"),
                "in_government": g.get("in_government"),
                "approval": g.get("approval"),
                "approval_state": g.get("approval_state"),
            }
            for g in igs_raw
        ]
        laws = [
            {"law": x.get("law"), "name": x.get("name")}
            for x in laws_raw
        ]
        pop = country.get("population") or {}
        professions = pop.get("by_profession") or {}
        top_prof = sorted(
            (
                {"name": k.split("|")[-1], "count": v}
                for k, v in professions.items()
            ),
            key=lambda r: r["count"],
            reverse=True,
        )[:8]
        cultures = s.cultures_resolved()[:8]
        return {
            "save": overview.get("save"),
            "save_path": str(s.save_path),
            "loaded_at": self.loaded_at,
            "mtime": self.save_mtime,
            "meta": overview.get("meta"),
            "country": overview.get("country"),
            "great_powers": overview.get("great_powers"),
            "interest_groups": igs,
            "laws": laws,
            "journal": journal,
            "military": {
                "army_count": military.get("army_count"),
                "navy_count": military.get("navy_count"),
            },
            "tech_count": tech.get("count"),
            "population_detail": {
                "total": pop.get("total"),
                "lower": pop.get("lower"),
                "middle": pop.get("middle"),
                "upper": pop.get("upper"),
                "unemployed": pop.get("unemployed_workforce"),
                "professions": top_prof,
                "cultures": cultures,
            },
            "analysis": {
                "headline": analysis.get("headline"),
                "flags": analysis.get("flags"),
                "advice": analysis.get("advice"),
                "government_clout": analysis.get("government_clout"),
                "government_igs": analysis.get("government_igs"),
            },
        }

    def _seed_actions(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        flags = analysis.get("flags") or []
        advice = analysis.get("advice") or []
        used_advice = set()
        actions = []
        for flag in flags:
            fid = str(flag.get("id") or "")
            mapped = FLAG_TO_ACTION.get(fid)
            if not mapped:
                level = flag.get("level") or "med"
                priority = {"high": "now", "med": "year", "low": "mid"}.get(level, "year")
                mapped = ("politics", priority, flag.get("text") or fid)
            direction, priority, title = mapped
            detail = flag.get("text") or ""
            reason = ""
            for a in advice:
                if a in used_advice:
                    continue
                # pair first unused advice line that shares a keyword
                reason = a
                used_advice.add(a)
                break
            actions.append(
                {
                    "id": f"flag-{fid or title}",
                    "direction": direction,
                    "direction_label": DIR_LABEL.get(direction, direction),
                    "priority": priority,
                    "priority_label": PRIORITY_LABEL.get(priority, priority),
                    "title": title,
                    "detail": detail,
                    "reason": reason,
                    "source": "heuristic",
                }
            )
        return actions[:16]


HUB = SaveHub()
