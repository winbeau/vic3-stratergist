"""OpenAI-compatible Vic3 advisor with save tools + advice-board updates."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from vic3_mcp.hub import HUB
from vic3_mcp.llm_settings import load_settings

SYSTEM = """你是维多利亚 3（Victoria 3）战役顾问。玩家正在网页里一边看存档看板，一边和你对话。

原则：
- 用简体中文。先听清玩家意图（想打仗、搞经济、改革、活过鸦片、稳住统一等），再给可执行建议。
- 数字必须来自工具返回的存档，禁止编造 GDP、人口、金库、法案。
- 不确定就调用工具。常用：get_dashboard、get_politics、get_economy、get_military、get_journal。
- 当你已经理解意图并有具体动作时，调用 set_advice_board，把建议写成看板卡片。
- 看板动作要短、可执行，分方向（politics/economy/military/diplomacy/tech/society）和优先级（now/year/mid）。
- 对话里用自然段落说话，不要把整张看板再贴一遍。可以问一句确认意图的问题。
- 当前默认玩家是大清开局时，优先：活过英国压力、金库变建筑、别硬刚乡绅、盯「脆弱的统一」。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_dashboard",
            "description": "当前存档指标总览：日期、GDP、金库、人口、法案摘要、风险旗标。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_politics",
            "description": "利益集团、法案、机构、人物。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_economy",
            "description": "金库、周收支、税率、GDP。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pops",
            "description": "人口结构、职业、文化、失业。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_diplomacy",
            "description": "关系、协定、战争、恶名。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_military",
            "description": "陆军/海军编制。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technology",
            "description": "已研究科技。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_journal",
            "description": "激活的日志条目。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_buildings",
            "description": "建筑等级与亏损建筑。",
            "parameters": {"type": "object", "properties": {"country": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_countries",
            "description": "对比多个国家。tags 逗号分隔，如 CHI,GBR,RUS。",
            "parameters": {
                "type": "object",
                "properties": {"tags": {"type": "string"}},
                "required": ["tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_advice_board",
            "description": "更新网页右侧建议动作看板。有明确下一步时必须调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "一句话概括玩家当前意图",
                    },
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "direction": {
                                    "type": "string",
                                    "enum": [
                                        "politics",
                                        "economy",
                                        "military",
                                        "diplomacy",
                                        "tech",
                                        "society",
                                    ],
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["now", "year", "mid"],
                                },
                                "title": {"type": "string"},
                                "detail": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                            "required": ["direction", "priority", "title"],
                        },
                    },
                },
                "required": ["actions"],
            },
        },
    },
]


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _sess():
    if HUB.session is None:
        HUB.refresh()
    if HUB.session is None:
        raise RuntimeError("存档尚未载入")
    return HUB.session


def run_tool(name: str, args: dict[str, Any]) -> str:
    country = args.get("country") or "player"
    try:
        if name == "get_dashboard":
            if HUB.dashboard is None:
                HUB.refresh()
            d = HUB.dashboard or {}
            slim = {
                "meta": d.get("meta"),
                "country": d.get("country"),
                "great_powers": d.get("great_powers"),
                "interest_groups": d.get("interest_groups"),
                "laws": d.get("laws"),
                "journal": d.get("journal"),
                "military": d.get("military"),
                "tech_count": d.get("tech_count"),
                "analysis": d.get("analysis"),
            }
            return _dumps(slim)
        if name == "get_politics":
            return _dumps(_sess().politics(country))
        if name == "get_economy":
            c = _sess().country(country)
            return _dumps({"tag": c.get("tag"), "name": c.get("name"), "gdp": c.get("gdp"), "treasury": c.get("treasury"), "tax_level": c.get("tax_level")})
        if name == "get_pops":
            s = _sess()
            c = s.country(country)
            return _dumps({"tag": c.get("tag"), "population": c.get("population"), "sol": c.get("sol"), "literacy": c.get("literacy"), "cultures": s.cultures_resolved(country)[:15]})
        if name == "get_diplomacy":
            s = _sess()
            c = s.country(country)
            return _dumps({"tag": c.get("tag"), "infamy": c.get("infamy"), **s.diplomacy(country)})
        if name == "get_military":
            return _dumps(_sess().military(country))
        if name == "get_technology":
            t = _sess().technology(country)
            return _dumps({"count": t.get("count"), "acquired": [x.get("id") for x in (t.get("acquired") or [])], "researching": t.get("researching")})
        if name == "get_journal":
            return _dumps(_sess().journal(country))
        if name == "get_buildings":
            return _dumps(_sess().buildings(country, top_n=20))
        if name == "compare_countries":
            tags = [x.strip() for x in str(args.get("tags") or "").split(",") if x.strip()]
            return _dumps(_sess().compare(tags or ["CHI", "GBR"]))
        if name == "set_advice_board":
            board = HUB.set_board(intent=args.get("intent"), actions=args.get("actions") or [])
            return _dumps({"ok": True, "count": len(board.get("actions") or []), "intent": board.get("intent")})
        return _dumps({"error": f"unknown tool {name}"})
    except Exception as exc:  # noqa: BLE001
        return _dumps({"error": str(exc)})


def _client() -> OpenAI:
    s = load_settings()
    if not s.get("api_key"):
        raise RuntimeError("未配置 API Key。请在设置里填写。")
    return OpenAI(api_key=s["api_key"], base_url=s["base_url"], timeout=120.0)


def _msg_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                parts.append(block.get("text") or "")
            else:
                t = getattr(block, "text", None)
                if t:
                    parts.append(t)
        if parts:
            return "".join(parts)
    reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
    if content:
        return content
    return reasoning or ""


def chat_events(messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield SSE-able dicts: token / tool / actions / error / done."""
    settings = load_settings()
    client = _client()
    model = settings["model"]

    if HUB.session is None:
        yield {"event": "tool", "data": {"name": "load_save", "status": "running"}}
        HUB.refresh()
        yield {"event": "tool", "data": {"name": "load_save", "status": "done"}}

    snap = ""
    if HUB.dashboard:
        c = (HUB.dashboard.get("country") or {})
        snap = (
            f"\n\n当前看板快照：{c.get('name')} {c.get('tag')} 日期{(HUB.dashboard.get('meta') or {}).get('game_date')}"
            f" GDP={c.get('gdp')} 人口={c.get('population')} 金库={(c.get('treasury') or {}).get('money')}"
            f" 等级={c.get('rank')} 头条={(HUB.dashboard.get('analysis') or {}).get('headline')}"
        )

    oai_messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM + snap}]
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            oai_messages.append({"role": role, "content": content})

    for _round in range(8):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=oai_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.4,
            )
        except Exception as exc:  # noqa: BLE001
            yield {"event": "error", "data": {"message": str(exc)}}
            return

        choice = resp.choices[0]
        msg = choice.message
        tool_calls = list(msg.tool_calls or [])
        if tool_calls:
            assistant_tool_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in tool_calls
                ],
            }
            oai_messages.append(assistant_tool_msg)
            for tc in tool_calls:
                fname = tc.function.name
                yield {"event": "tool", "data": {"name": fname, "status": "running"}}
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(fname, args if isinstance(args, dict) else {})
                if fname == "set_advice_board":
                    yield {"event": "actions", "data": HUB.board}
                oai_messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result[:24000]}
                )
                yield {"event": "tool", "data": {"name": fname, "status": "done"}}
            continue

        text = _msg_text(msg)
        if text:
            yield {"event": "token", "data": {"text": text}}
        yield {"event": "actions", "data": HUB.board}
        yield {"event": "done", "data": {"text": text}}
        return

    yield {"event": "error", "data": {"message": "工具调用轮次过多"}}
