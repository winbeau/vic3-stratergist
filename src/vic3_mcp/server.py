"""Victoria 3 MCP server — read local saves and answer campaign questions."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from vic3_mcp.gamedata import loc
from vic3_mcp.session import Vic3Session, continue_save_hint, list_save_files

INSTRUCTIONS = """\
Victoria 3 本机存档读取器。给玩家（默认大清 Qing_MCP）做局势分析。

推荐调用顺序：
1. list_saves / load_save 载入存档
2. overview 看日期、GDP、金库、人口、等级
3. analyze_situation 看风险与建议
4. 按需再调 politics / economy / pops / diplomacy / military / technology / journal / buildings

国家参数 country 可以是标签（CHI、GBR）、数字 id、或 player。
"""

mcp = FastMCP("vic3", instructions=INSTRUCTIONS)

_SESSION: Vic3Session | None = None
_LANG = "simp_chinese"


def _session() -> Vic3Session:
    global _SESSION
    if _SESSION is None:
        hint = continue_save_hint() or "Qing_MCP"
        _SESSION = Vic3Session.load(hint, lang=_LANG)
    return _SESSION


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@mcp.tool()
def list_saves() -> str:
    """列出本机 Victoria 3 存档（Documents/Paradox Interactive/Victoria 3/save games）。"""
    rows = list_save_files()
    return _json({"continue": continue_save_hint(), "saves": rows, "count": len(rows)})


@mcp.tool()
def load_save(name: str = "Qing_MCP", lang: str = "simp_chinese") -> str:
    """融化并载入一个 .v3 存档。name 可以是存档名（如 Qing_MCP）或完整路径。"""
    global _SESSION, _LANG
    _LANG = lang or "simp_chinese"
    _SESSION = Vic3Session.load(name, lang=_LANG)
    s = _SESSION
    player = s.country_map.get(s.player_id or -1, {})
    return _json(
        {
            "loaded": s.save_path.name,
            "melted": str(s.melted_path),
            "version": s.meta.get("version"),
            "date": s.meta.get("game_date"),
            "save_name": s.meta.get("save_name"),
            "player_id": s.player_id,
            "player_tag": player.get("tag"),
            "countries": len(s.country_map),
            "top_level_keys": list(s.index.keys()),
        }
    )


@mcp.tool()
def overview(country: str = "player") -> str:
    """国家总览：日期、等级、GDP、威望、生活水平、人口、金库与列强名单。"""
    return _json(_session().overview(country))


@mcp.tool()
def analyze_situation(country: str = "player") -> str:
    """根据存档数据给出风险标记和可执行建议（大清 1836 会附开局打法）。"""
    return _json(_session().analysis(country))


@mcp.tool()
def country(tag: str = "player") -> str:
    """单个国家的完整摘要（经济、人口、政府、省份列表）。"""
    return _json(_session().country(tag))


@mcp.tool()
def list_countries(limit: int = 30, sort: str = "gdp") -> str:
    """列出存档里的国家。sort: gdp | prestige | population | tag。"""
    s = _session()
    rows = list(s.country_map.values())
    key = {"gdp": "gdp", "prestige": "prestige", "population": "population", "tag": "tag"}.get(sort, "gdp")
    rows.sort(key=lambda r: (r.get(key) is None, -(r.get(key) or 0) if key != "tag" else 0, r.get("tag") or ""))
    slim = []
    for r in rows[: max(1, min(limit, 200))]:
        slim.append(
            {
                "id": r["id"],
                "tag": r.get("tag"),
                "name": loc(r.get("dynamic_name"), s.lang, None) or loc(r.get("tag"), s.lang, r.get("tag")),
                "type": r.get("country_type"),
                "gdp": r.get("gdp"),
                "prestige": r.get("prestige"),
                "population": r.get("population"),
                "sol": r.get("sol"),
            }
        )
    return _json({"sort": sort, "countries": slim})


@mcp.tool()
def economy(country: str = "player") -> str:
    """金库、周收支、投资池、税率。"""
    c = _session().country(country)
    return _json(
        {
            "tag": c["tag"],
            "name": c["name"],
            "gdp": c.get("gdp"),
            "tax_level": c.get("tax_level"),
            "treasury": c.get("treasury"),
        }
    )


@mcp.tool()
def politics(country: str = "player") -> str:
    """利益集团、法案、机构、统治者/继承人。"""
    return _json(_session().politics(country))


@mcp.tool()
def pops(country: str = "player") -> str:
    """人口结构：阶层、职业、文化、失业、生活水平。"""
    s = _session()
    c = s.country(country)
    return _json(
        {
            "tag": c["tag"],
            "name": c["name"],
            "sol": c.get("sol"),
            "literacy": c.get("literacy"),
            "population": c.get("population"),
            "cultures": s.cultures_resolved(country)[:20],
        }
    )


@mcp.tool()
def diplomacy(country: str = "player") -> str:
    """外交：关系、协定/敌对、战争。"""
    s = _session()
    c = s.country(country)
    d = s.diplomacy(country)
    return _json({"tag": c["tag"], "name": c["name"], "infamy": c.get("infamy"), **d})


@mcp.tool()
def military(country: str = "player") -> str:
    """陆军/海军编制。"""
    s = _session()
    c = s.country(country)
    return _json({"tag": c["tag"], "name": c["name"], **s.military(country)})


@mcp.tool()
def technology(country: str = "player") -> str:
    """已研究科技。"""
    s = _session()
    c = s.country(country)
    return _json({"tag": c["tag"], "name": c["name"], **s.technology(country)})


@mcp.tool()
def journal(country: str = "player") -> str:
    """该国激活的日志条目。"""
    s = _session()
    c = s.country(country)
    return _json({"tag": c["tag"], "name": c["name"], "entries": s.journal(country)})


@mcp.tool()
def buildings(country: str = "player", top_n: int = 30) -> str:
    """建筑汇总：按类型的等级、利润，以及亏损建筑。"""
    s = _session()
    c = s.country(country)
    return _json({"tag": c["tag"], "name": c["name"], **s.buildings(country, top_n=top_n)})


@mcp.tool()
def states(country: str = "player") -> str:
    """该国省份：名称、整合度、基础设施、人口。"""
    s = _session()
    c = s.country(country)
    return _json({"tag": c["tag"], "name": c["name"], "states": s.states(country)})


@mcp.tool()
def rankings() -> str:
    """威望排行与国家等级（列强/大国等）。"""
    return _json({"rankings": _session().rankings()[:80]})


@mcp.tool()
def compare_countries(tags: str = "CHI,GBR,RUS,FRA,USA,JAP") -> str:
    """对比多个国家的 GDP、威望、人口、科技数。tags 为逗号分隔标签。"""
    parts = [t.strip() for t in tags.split(",") if t.strip()]
    return _json({"compare": _session().compare(parts)})


@mcp.tool()
def search_save(query: str, max_hits: int = 25) -> str:
    """在融化后的存档文本里搜索原始字段（调试/查冷门数据）。"""
    return _json({"query": query, "hits": _session().search_melted(query, max_hits=max_hits)})


@mcp.tool()
def localize(keys: str) -> str:
    """查询游戏本地化。keys 为逗号分隔的 loc key，如 CHI,law_serfdom,ig_landowners。"""
    s = _session()
    parts = [k.strip() for k in keys.split(",") if k.strip()]
    return _json({k: loc(k, s.lang, None) for k in parts})


@mcp.prompt()
def vic3_advisor(country: str = "player") -> str:
    """让助手以维多利亚 3 顾问身份，基于当前存档给建议。"""
    return (
        f"你是 Victoria 3 战术/战略顾问。先用 vic3 MCP 的 load_save（若未载入）"
        f"和 overview、analyze_situation、politics、economy 读取国家 {country} 的存档数据，"
        "再给出分优先级的建议。区分：立刻要做、这一年要做、中期改革。"
        "不要编造存档里没有的数字；不确定就再调工具。"
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
