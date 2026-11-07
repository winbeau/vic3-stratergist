"""Turn extracted save data into flags and play advice."""

from __future__ import annotations

from typing import Any


def _law_ids(laws: list[dict[str, Any]]) -> set[str]:
    return {str(x.get("law") or "") for x in laws}


def analyze_country(
    *,
    meta: dict[str, Any],
    country: dict[str, Any],
    igs: list[dict[str, Any]],
    laws: list[dict[str, Any]],
    tech: dict[str, Any],
    journal: list[dict[str, Any]],
    diplomacy: dict[str, Any],
    military: dict[str, Any],
    buildings: dict[str, Any] | None = None,
    rankings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    flags: list[dict[str, str]] = []
    advice: list[str] = []
    tag = country.get("tag")
    date = str(meta.get("game_date") or "")
    treasury = country.get("treasury") or {}
    pop = country.get("population") or {}
    ctype = country.get("country_type")
    law_ids = _law_ids(laws)
    gov_igs = [g for g in igs if g.get("in_government")]
    gov_clout = sum(g.get("clout") or 0 for g in gov_igs)
    angry = [g for g in igs if (g.get("approval") is not None and g["approval"] <= -2) or g.get("approval_state") in {"angry", "unhappy"}]
    happy = [g for g in igs if g.get("approval_state") in {"happy", "loyal"}]

    if ctype and "unrecognized" in str(ctype):
        flags.append({"level": "high", "id": "unrecognized", "text": "未受承认：科技扩散慢、外交选项受限，被列强针对的风险更高。"})
        advice.append("把「获得列强承认」当成中期战略目标：提高威望、打赢承认战争、或达到被承认所需的科技/等级门槛。")

    if "law_canton_system" in law_ids or "law_isolationism" in law_ids:
        flags.append(
            {
                "level": "high",
                "id": "canton_system",
                "text": "广州一口通商/闭关：外贸被锁在极少口岸，市场价格畸形，且容易和英国因鸦片冲突。",
            }
        )
        advice.append("一口通商期间优先自给：工具、纸张、服装、武器。不要指望进口。鸦片战争前把沿海和武器备好。")
    if "law_closed_borders" in law_ids:
        flags.append({"level": "low", "id": "closed_borders", "text": "关闭边境：几乎没有移民，人口增长全靠自然增长。"})
    if "law_no_schools" in law_ids:
        flags.append({"level": "med", "id": "no_schools", "text": "没有学校机构，识字率很难涨。"})
        advice.append("有纸张和官僚容量后再上学校机构；宗教学校往往是乡绅/儒家能接受的第一步。")

    if "law_traditionalism" in law_ids:
        flags.append({"level": "high", "id": "traditionalism", "text": "传统主义经济：投资池效率极差，工业扩张会非常慢。"})
        advice.append("经济法案优先从传统主义改到农本（agrarianism），再视工业家力量转向干预主义。改法前先看地主/乡绅态度。")

    if "law_serfdom" in law_ids:
        flags.append({"level": "med", "id": "serfdom", "text": "农奴制：农民难进城，工业劳动力紧张。"})
        advice.append("有一定工业岗位后再废农奴，否则农民会大量失业/激化。")

    if "law_peasant_levies" in law_ids:
        flags.append({"level": "med", "id": "peasant_levies", "text": "农民征召：军队质量差，动员伤经济。"})
        advice.append("军事线尽早走向职业军队；在此之前避免和英国正面陆战硬刚，用数量、补给、地形和防御工事拖。")

    money = treasury.get("money") or 0
    credit = treasury.get("credit_limit") or 0
    used = treasury.get("credit_used_pct") or 0
    bal = treasury.get("weekly_balance") or 0
    if money < 0 and used > 50:
        flags.append({"level": "high", "id": "debt", "text": f"国债已用掉信用额度的 {used:.0f}%。"})
        advice.append("停掉亏损补贴、降低行政楼超编、或临时加税。破产会毁掉投资池和利率。")
    elif money > 0 and bal < 0:
        flags.append({"level": "med", "id": "gold_drain", "text": "金库还在，但周结余为负，金库会被打穿。"})
    elif money > 0 and (country.get("gdp") or 0) and money > 0.2 * (country.get("gdp") or 1):
        flags.append({"level": "low", "id": "over_saving", "text": "金库相对 GDP 偏高，闲钱没有变成建筑。"})
        advice.append("把金库花在建筑部门、大学、兵工厂和港口上，不要屯金。")

    sol = country.get("sol") or 0
    if sol and sol < 10:
        flags.append({"level": "med", "id": "low_sol", "text": f"平均生活水平 {sol:.1f}，激进派温床。"})
        advice.append("优先粮食/服装/家具供给和降低税负；工业建设不要饿着消费品。")

    lit = country.get("literacy")
    if lit is not None and 0 < lit < 0.2:
        flags.append({"level": "med", "id": "literacy", "text": f"识字率偏低（{lit:.1%}），科研和职业资格会卡住。"})
        advice.append("有纸张供给后盖大学；学校机构能上就上。识字是承认和工业化的前置。")

    unemp = pop.get("unemployed_workforce") or 0
    if unemp > 200_000:
        flags.append({"level": "med", "id": "unemployment", "text": f"失业劳动力约 {unemp:,.0f}。"})

    peasants = 0
    for k, v in (pop.get("by_profession") or {}).items():
        if k.startswith("peasants"):
            peasants = v
    total_pop = pop.get("total") or 1
    if peasants and peasants / total_pop > 0.8:
        flags.append({"level": "low", "id": "peasant_society", "text": f"农民占总人口 {peasants / total_pop:.0%}，仍是农业帝国。"})

    if gov_clout < 0.5:
        flags.append({"level": "high", "id": "illegitimate", "text": f"执政利益集团总影响力 {gov_clout:.0%}，合法性会很差。"})
        advice.append("把高影响力且不极端的 IG 拉进政府，或先别硬改他们讨厌的法。")
    landowners = next((g for g in igs if g.get("definition") == "ig_landowners"), None)
    if landowners and (landowners.get("clout") or 0) > 0.35:
        flags.append({"level": "med", "id": "landowner_power", "text": f"地主/乡绅影响力 {landowners['clout']:.0%}，改革会被卡住。"})
        advice.append("削弱地主：减少庄园、提高其他 IG 的政治力量（军队、知识分子、工业家），不要一上来全面开战。")

    if angry:
        flags.append(
            {
                "level": "high",
                "id": "angry_igs",
                "text": "不满 IG：" + "、".join(g.get("name") or g.get("definition") for g in angry),
            }
        )

    je_types = {j.get("type") or "" for j in journal}
    if any("opium" in t for t in je_types):
        flags.append({"level": "high", "id": "opium", "text": "鸦片相关日志已激活。"})
        advice.append("鸦片事件链是大清开局核心：备战海军/沿海、囤武器、考虑迁都或死守北京的取舍，不要在事件中途拆光军队。")
    if any("taiping" in t or "heavenly" in t for t in je_types):
        flags.append({"level": "high", "id": "taiping", "text": "太平天国/内乱日志。"})
    if any("warlord" in t or t == "je_warlord_china" for t in je_types):
        flags.append({"level": "high", "id": "warlord_china", "text": "「脆弱的统一」日志：内地动荡/军阀风险，需要维持正统与军队。"})
        advice.append("盯着脆弱的统一进度：别把所有军队调去沿海而把内地掏空，也不要无限制激怒乡绅。")

    acquired = {t.get("id") for t in (tech.get("acquired") or [])}
    military_basics = {"military_drill", "line_infantry", "napoleonic_warfare", "artillery"}
    missing_mil = sorted(military_basics - acquired)
    if missing_mil:
        advice.append("军事科技缺口：" + "、".join(missing_mil) + "。被英国打之前至少把队列/火炮补上。")

    if military.get("navy_count", 0) == 0:
        flags.append({"level": "med", "id": "no_navy", "text": "没有舰队编制，沿海会被封锁。"})

    unprof = (buildings or {}).get("unprofitable") or []
    if len(unprof) >= 8:
        flags.append({"level": "med", "id": "unprofitable_buildings", "text": f"{len(unprof)} 类建筑在亏损。"})
        advice.append("先看工具/煤/铁的价格和短缺，再决定是改生产方式还是补贴。乱补会烧预算。")

    rank_row = None
    if rankings:
        rank_row = next((r for r in rankings if r.get("tag") == tag), None)
        gps = [r for r in rankings if r.get("rank") == "great_power"]
        if gps:
            advice.append(
                "当前列强："
                + "、".join(f"{g.get('name') or g.get('tag')}(威望{g.get('prestige')})" for g in gps[:8])
            )

    # Qing opener
    opener = None
    if tag == "CHI" and date.startswith("1836"):
        opener = [
            "这是 1836 大清开局：人口与 GDP 世界第一，但未受承认、闭关、传统主义、农奴制、农民征召叠在一起。",
            "第一条命：活过鸦片战争。沿海炮台、武器库存、合理的征兵，不要在外交上主动加英国的怒。",
            "第二条命：钱和建筑。金库有余就盖建筑部门（先在高基础设施的直隶/江南），行政楼够用即可，官僚浪费是大清开局常见坑。",
            "第三条命：法案顺序建议 传统主义→农本，孤立主义等打完/谈完鸦片再动，农奴制等有工厂岗位再废。",
            "乡绅（地主）超过一半影响力，所有改革都要看他们的脸。先拉军队/儒家/知识分子，别一上来全面自由派。",
            "科研：殖民/军事/银行学里选能提高承认、军队和建筑效率的；大学要有纸张。",
            "内政：盯粮价、鸦片种植园、地方起义日志；人口巨大，激进派绝对值会吓人，看比例和 IG 态度。",
        ]
        advice = opener + advice

    flags.sort(key=lambda f: {"high": 0, "med": 1, "low": 2}.get(f["level"], 9))
    # de-dupe advice while preserving order
    seen: set[str] = set()
    uniq = []
    for a in advice:
        if a not in seen:
            seen.add(a)
            uniq.append(a)

    return {
        "date": date,
        "tag": tag,
        "name": country.get("name"),
        "rank_row": rank_row,
        "government_clout": round(gov_clout, 3),
        "government_igs": [g.get("definition") for g in gov_igs],
        "happy_igs": [g.get("definition") for g in happy],
        "flags": flags,
        "advice": uniq,
        "headline": flags[0]["text"] if flags else "没有明显的结构性危机，按建设与科技推进即可。",
    }
