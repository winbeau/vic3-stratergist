"""Pull structured campaign data out of a melted Victoria 3 save."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from vic3_mcp.clausewitz import (
    as_dict,
    as_list,
    first_scalar,
    iter_database_entries,
    last_channel_value,
    parse_text,
)
from vic3_mcp.gamedata import (
    EXPENSE_LABELS,
    INCOME_LABELS,
    POP_TYPES,
    STRATA,
    loc,
    pop_type_name,
)

SCALE_100K = 100_000.0

SKIP_IG_KEYS = frozenset({"pops"})
SKIP_BUILDING_KEYS = frozenset({"input_goods", "output_goods", "owners", "assets"})
SKIP_STATE_KEYS = frozenset({"pop_needs", "provinces"})
SKIP_CHAR_KEYS = frozenset()


def unwrap_entry(entry_id: int, text: str) -> dict[str, Any]:
    obj = parse_text(text)
    if isinstance(obj, dict):
        inner = obj.get(str(entry_id), obj.get(entry_id))
        if isinstance(inner, dict):
            return inner
        if len(obj) == 1:
            only = next(iter(obj.values()))
            if isinstance(only, dict):
                return only
        return obj
    return {}


def _num(v: Any, default: float | None = None) -> float | None:
    if v is None:
        return default
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int | None = None) -> int | None:
    n = _num(v)
    return int(n) if n is not None else default


def _label_array(values: Any, labels: list[str]) -> dict[str, float]:
    if not isinstance(values, list):
        return {}
    out: dict[str, float] = {}
    for i, raw in enumerate(values):
        n = _num(raw)
        if n is None or n == 0:
            continue
        name = labels[i] if i < len(labels) else f"slot_{i}"
        out[name] = round(n, 2)
    return out


def _named_money_map(block: Any) -> dict[str, float]:
    block = as_dict(block)
    values = as_dict(block.get("values"))
    out: dict[str, float] = {}
    for k, v in values.items():
        n = _num(v)
        if n is None:
            continue
        out[str(k)] = round(n, 2)
    return out


def _maybe_scale_pop(n: float) -> float:
    # Culture/religion buckets in 1.13 are stored in units of 100k people.
    if abs(n) < 50_000:
        return n * SCALE_100K
    return n


def extract_meta(melted, index: dict[str, tuple[int, int]]) -> dict[str, Any]:
    from vic3_mcp.clausewitz import read_section

    start, end = index["meta_data"]
    raw = parse_text(read_section(melted, start, end))
    meta = as_dict(raw.get("meta_data") if isinstance(raw, dict) else {})
    if not meta and isinstance(raw, dict):
        meta = raw
    date = meta.get("game_date")
    if "date" in index:
        ds, de = index["date"]
        date_obj = parse_text(read_section(melted, ds, de))
        if isinstance(date_obj, dict) and date_obj.get("date"):
            date = date_obj.get("date")
    player_id = None
    if "player_manager" in index:
        ps, pe = index["player_manager"]
        pm = parse_text(read_section(melted, ps, pe))
        wrapped = as_dict(pm.get("player_manager") or pm)
        db = as_dict(wrapped.get("database"))
        for rec in db.values():
            if isinstance(rec, dict) and rec.get("country") is not None:
                player_id = _i(rec.get("country"))
                break
    if player_id is None and "previous_played" in index:
        ps, pe = index["previous_played"]
        pp = parse_text(read_section(melted, ps, pe))
        blob = as_dict(pp.get("previous_played") or pp)
        items = as_list(blob.get("_items") or blob.get("previous_played") or [])
        for it in items:
            if isinstance(it, dict) and it.get("idtype") is not None:
                player_id = _i(it.get("idtype"))
                break
    rules = as_dict(meta.get("game_rules")).get("settings")
    rule_list = as_list(as_dict(rules).get("_values") if isinstance(rules, dict) else rules)
    return {
        "version": meta.get("version"),
        "game_date": date,
        "save_name": meta.get("name"),
        "rank": meta.get("rank"),
        "ironman": meta.get("ironman"),
        "dlcs": as_list(as_dict(meta.get("dlcs")).get("_values") or meta.get("dlcs")),
        "game_rules": [str(x) for x in rule_list],
        "player_country_id": player_id,
        "number_of_players": meta.get("number_of_players"),
    }


def _unwrap_manager(obj: dict[str, Any], manager_key: str) -> dict[str, Any]:
    if manager_key in obj and isinstance(obj[manager_key], dict):
        return obj[manager_key]
    return obj


def build_country_map(melted, index: dict[str, tuple[int, int]]) -> dict[int, dict[str, Any]]:
    """id -> compact country row (tag, gdp, prestige, money, infamy)."""
    start, end = index["country_manager"]
    rows: dict[int, dict[str, Any]] = {}
    for eid, text in iter_database_entries(melted, start, end):
        data = unwrap_entry(eid, text)
        if not data or data.get("definition") is None:
            continue
        tag = str(data["definition"])
        budget = as_dict(data.get("budget"))
        pop = as_dict(data.get("pop_statistics"))
        lower = _num(pop.get("population_lower_strata"), 0) or 0
        mid = _num(pop.get("population_middle_strata"), 0) or 0
        upper = _num(pop.get("population_upper_strata"), 0) or 0
        dyn = as_dict(data.get("dynamic_name"))
        rows[eid] = {
            "id": eid,
            "tag": tag,
            "government": data.get("government"),
            "country_type": data.get("country_type"),
            "dynamic_name": dyn.get("dynamic_country_name"),
            "gdp": last_channel_value(data.get("gdp")),
            "prestige": last_channel_value(data.get("prestige")),
            "literacy": last_channel_value(data.get("literacy")),
            "sol": last_channel_value(data.get("avgsoltrend")),
            "money": _num(budget.get("money")),
            "credit": _num(budget.get("credit")),
            "infamy": _num(data.get("infamy"), 0) or 0,
            "tax_level": data.get("tax_level"),
            "population": int(lower + mid + upper),
            "num_states": len(as_list(as_dict(data.get("states")).get("_values") or data.get("states"))),
        }
        states = data.get("states")
        if isinstance(states, list):
            rows[eid]["state_ids"] = [int(x) for x in states if isinstance(x, (int, float))]
        elif isinstance(states, dict):
            vals = states.get("_values")
            if isinstance(vals, list):
                rows[eid]["state_ids"] = [int(x) for x in vals if isinstance(x, (int, float))]
    return rows


def extract_country(
    melted,
    index: dict[str, tuple[int, int]],
    country_id: int,
    *,
    lang: str = "simp_chinese",
) -> dict[str, Any]:
    start, end = index["country_manager"]
    data: dict[str, Any] | None = None
    for eid, text in iter_database_entries(melted, start, end):
        if eid != country_id:
            continue
        data = unwrap_entry(eid, text)
        break
    if not data:
        raise KeyError(f"country id {country_id} not found")
    return format_country(data, country_id, lang=lang)


def format_country(data: dict[str, Any], country_id: int, *, lang: str = "simp_chinese") -> dict[str, Any]:
    budget = as_dict(data.get("budget"))
    building_budget = as_dict(budget.get("country_building_budget"))
    expenses_named: dict[str, Any] = {}
    incomes_named: dict[str, Any] = {}
    for bucket, target in (
        ("government_goods", expenses_named),
        ("government_wages", expenses_named),
        ("military_goods", expenses_named),
        ("military_wages", expenses_named),
        ("subsidies", expenses_named),
        ("subventions", expenses_named),
        ("construction_goods", expenses_named),
        ("government_share_losses", expenses_named),
    ):
        named = _named_money_map(as_dict(building_budget.get("expenses")).get(bucket))
        if named:
            expenses_named[bucket] = named
    for bucket in (
        "income_taxes",
        "poll_taxes",
        "tariffs",
        "minting",
        "diplomatic_pacts",
        "interest",
        "additional_income",
    ):
        named = _named_money_map(as_dict(building_budget.get("incomes")).get(bucket))
        if named:
            incomes_named[bucket] = named

    pop = as_dict(data.get("pop_statistics"))
    lower = _num(pop.get("population_lower_strata"), 0) or 0
    mid = _num(pop.get("population_middle_strata"), 0) or 0
    upper = _num(pop.get("population_upper_strata"), 0) or 0
    professions = _profession_map(pop.get("population_by_profession"), lang)
    cultures_raw = as_dict(pop.get("population_by_culture"))
    cultures = {
        str(k): int(round(_maybe_scale_pop(_num(v, 0) or 0)))
        for k, v in cultures_raw.items()
        if _num(v) is not None
    }
    dyn = as_dict(data.get("dynamic_name"))
    tag = str(data.get("definition") or "")
    states = data.get("states")
    state_ids: list[int] = []
    if isinstance(states, list):
        state_ids = [int(x) for x in states if isinstance(x, (int, float))]
    elif isinstance(states, dict):
        vals = states.get("_values")
        if isinstance(vals, list):
            state_ids = [int(x) for x in vals if isinstance(x, (int, float))]

    money = _num(budget.get("money"), 0) or 0
    credit = _num(budget.get("credit"), 0) or 0
    weekly_income = as_list(budget.get("weekly_income"))
    weekly_expense = as_list(budget.get("weekly_expenses"))
    inc_sum = sum(_num(x, 0) or 0 for x in weekly_income)
    exp_sum = sum(_num(x, 0) or 0 for x in weekly_expense)

    display = loc(dyn.get("dynamic_country_name"), lang, None) or loc(tag, lang, tag)
    return {
        "id": country_id,
        "tag": tag,
        "name": display,
        "name_key": dyn.get("dynamic_country_name") or tag,
        "government": data.get("government"),
        "government_name": loc(data.get("government"), lang, data.get("government")),
        "country_type": data.get("country_type"),
        "religion": data.get("religion"),
        "religion_name": loc(data.get("religion"), lang, data.get("religion")),
        "ruler_id": data.get("ruler"),
        "heir_id": data.get("heir"),
        "capital_state_id": data.get("capital"),
        "market_id": data.get("market"),
        "tax_level": data.get("tax_level"),
        "infamy": _num(data.get("infamy"), 0) or 0,
        "gdp": last_channel_value(data.get("gdp")),
        "prestige": last_channel_value(data.get("prestige")),
        "literacy": last_channel_value(data.get("literacy")),
        "sol": last_channel_value(data.get("avgsoltrend")),
        "treasury": {
            "money": round(money, 2),
            "credit_limit": round(credit, 2),
            "debt_or_gold": round(money, 2),
            "credit_used_pct": round(max(0, -money) / credit * 100, 2) if credit else 0,
            "gold_reserves": round(money, 2) if money > 0 else 0,
            "debt": round(-money, 2) if money < 0 else 0,
            "weekly_income_total": round(inc_sum, 2),
            "weekly_expense_total": round(exp_sum, 2),
            "weekly_balance": round(inc_sum - exp_sum, 2),
            "income_by_category": _label_array(weekly_income, INCOME_LABELS),
            "expense_by_category": _label_array(weekly_expense, EXPENSE_LABELS),
            "building_income": round(_num(building_budget.get("income"), 0) or 0, 2),
            "building_expense": round(_num(building_budget.get("expense"), 0) or 0, 2),
            "investment_pool_change": round(
                _num(budget.get("weekly_investment_pool_change_from_investment"), 0) or 0, 2
            ),
            "average_productivity": _num(budget.get("average_productivity")),
        },
        "population": {
            "total": int(lower + mid + upper),
            "lower": int(lower),
            "middle": int(mid),
            "upper": int(upper),
            "political_participants": int(_num(pop.get("population_political_participants"), 0) or 0),
            "salaried_workforce": int(_num(pop.get("population_salaried_workforce"), 0) or 0),
            "unemployed_workforce": int(_num(pop.get("population_unemployed_workforce"), 0) or 0),
            "laborer_workforce": int(_num(pop.get("population_laborer_workforce"), 0) or 0),
            "government_workforce": int(_num(pop.get("population_government_workforce"), 0) or 0),
            "military_workforce": int(_num(pop.get("population_military_workforce"), 0) or 0),
            "by_profession": professions,
            "by_culture_id": cultures,
            "radicals": last_channel_value(pop.get("trend_radicals")),
            "loyalists": last_channel_value(pop.get("trend_loyalists")),
        },
        "state_ids": state_ids,
        "num_states": len(state_ids),
        "counters": as_dict(data.get("counters")),
        "cultures": as_list(as_dict(data.get("cultures")).get("_values") or data.get("cultures")),
    }


def _profession_map(raw: Any, lang: str) -> dict[str, int]:
    data = as_dict(raw)
    out: dict[str, int] = {}
    for k, v in data.items():
        n = _num(v)
        if n is None:
            continue
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        ident = POP_TYPES[idx] if 0 <= idx < len(POP_TYPES) else f"type_{idx}"
        out[f"{ident}|{pop_type_name(idx, lang)}"] = int(n)
    return out


def extract_rankings(melted, index, country_map: dict[int, dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    if "country_rankings" not in index:
        return []
    from vic3_mcp.clausewitz import read_section

    start, end = index["country_rankings"]
    obj = parse_text(read_section(melted, start, end))
    inner = as_dict(obj.get("country_rankings") or obj)
    rows = inner.get("country_rankings")
    items: list[Any]
    if isinstance(rows, list):
        items = rows
    elif isinstance(rows, dict):
        items = as_list(rows.get("_items") or list(rows.values()))
    else:
        items = []
    out = []
    for rec in items:
        if not isinstance(rec, dict):
            continue
        cid = _i(rec.get("country"))
        info = country_map.get(cid or -1, {})
        tag = info.get("tag")
        out.append(
            {
                "score": rec.get("score"),
                "rank": rec.get("rank"),
                "target_rank": rec.get("target"),
                "prestige": rec.get("prestige"),
                "country_id": cid,
                "tag": tag,
                "name": loc(info.get("dynamic_name"), lang, None) or loc(tag, lang, tag),
                "gdp": info.get("gdp"),
                "population": info.get("population"),
                "country_type": info.get("country_type"),
            }
        )
    out.sort(key=lambda r: (_i(r.get("score"), 9999) or 9999))
    return out


def extract_interest_groups(melted, index, country_id: int, lang: str) -> list[dict[str, Any]]:
    start, end = index["interest_groups"]
    out = []
    for eid, text in iter_database_entries(melted, start, end, skip_keys=SKIP_IG_KEYS):
        data = unwrap_entry(eid, text)
        if _i(data.get("country")) != country_id:
            continue
        definition = str(data.get("definition") or data.get("name") or "")
        out.append(
            {
                "id": eid,
                "definition": definition,
                "name": loc(data.get("name"), lang, None) or loc(definition, lang, definition),
                "in_government": bool(data.get("in_government")),
                "clout": round(_num(data.get("clout"), 0) or 0, 4),
                "approval": _num(data.get("approval")),
                "approval_state": data.get("approval_state"),
                "political_strength": _num(data.get("political_strength")),
                "leader_id": data.get("leader"),
                "influence_type": data.get("influence_type"),
                "ideologies": as_list(as_dict(data.get("ideologies")).get("_values") or data.get("ideologies")),
                "traits": as_list(as_dict(data.get("traits")).get("_values") or data.get("traits")),
                "enabled_traits": as_list(
                    as_dict(data.get("enabled_traits")).get("_values") or data.get("enabled_traits")
                ),
            }
        )
    out.sort(key=lambda x: x.get("clout") or 0, reverse=True)
    return out


def extract_laws(melted, index, country_id: int, lang: str) -> list[dict[str, Any]]:
    start, end = index["laws"]
    out = []
    for eid, text in iter_database_entries(melted, start, end):
        data = unwrap_entry(eid, text)
        if _i(data.get("country")) != country_id:
            continue
        if not data.get("active"):
            continue
        law = str(data.get("law") or "")
        out.append(
            {
                "id": eid,
                "law": law,
                "name": loc(law, lang, law),
                "activation_date": data.get("activation_date"),
            }
        )
    out.sort(key=lambda x: x["law"])
    return out


def extract_institutions(melted, index, country_id: int, lang: str) -> list[dict[str, Any]]:
    if "institutions" not in index:
        return []
    start, end = index["institutions"]
    out = []
    for eid, text in iter_database_entries(melted, start, end):
        data = unwrap_entry(eid, text)
        if _i(data.get("country")) != country_id:
            continue
        ident = str(data.get("institution") or data.get("type") or data.get("name") or "")
        out.append(
            {
                "id": eid,
                "institution": ident,
                "name": loc(ident, lang, ident),
                "investment": data.get("investment") or data.get("level"),
                "raw": {k: v for k, v in data.items() if k not in {"country"} and not isinstance(v, (dict, list))},
            }
        )
    return out


def extract_technology(melted, index, country_id: int, lang: str) -> dict[str, Any]:
    start, end = index["technology"]
    for eid, text in iter_database_entries(melted, start, end):
        data = unwrap_entry(eid, text)
        if _i(data.get("country")) != country_id:
            continue
        techs = as_list(as_dict(data.get("acquired_technologies")).get("_values") or data.get("acquired_technologies"))
        techs = [str(t) for t in techs]
        return {
            "acquired": [{"id": t, "name": loc(t, lang, t)} for t in techs],
            "count": len(techs),
            "researching": data.get("researching") or data.get("current_tech"),
            "innovation": _num(data.get("innovation")),
            "raw_keys": [k for k in data.keys() if k not in {"country", "acquired_technologies"}],
        }
    return {"acquired": [], "count": 0}


def extract_journal(melted, index, country_id: int, lang: str) -> list[dict[str, Any]]:
    start, end = index["journal_entry_manager"]
    out = []
    for eid, text in iter_database_entries(melted, start, end):
        data = unwrap_entry(eid, text)
        if _i(data.get("country")) != country_id:
            continue
        if data.get("active") is False:
            continue
        typ = str(data.get("type") or "")
        out.append(
            {
                "id": eid,
                "type": typ,
                "name": loc(typ, lang, typ),
                "active": data.get("active"),
                "date_added": data.get("date_added"),
                "baseline_value": data.get("baseline_value"),
                "goal_value": data.get("goal_value"),
            }
        )
    return out


def extract_diplomacy(
    melted, index, country_id: int, country_map: dict[int, dict[str, Any]], lang: str
) -> dict[str, Any]:
    pacts = []
    if "pacts" in index:
        start, end = index["pacts"]
        for eid, text in iter_database_entries(melted, start, end):
            data = unwrap_entry(eid, text)
            targets = as_dict(data.get("targets"))
            first, second = _i(targets.get("first")), _i(targets.get("second"))
            if country_id not in {first, second}:
                continue
            other = second if first == country_id else first
            info = country_map.get(other or -1, {})
            pacts.append(
                {
                    "id": eid,
                    "action": data.get("action"),
                    "other_id": other,
                    "other_tag": info.get("tag"),
                    "other_name": loc(info.get("dynamic_name"), lang, None) or loc(info.get("tag"), lang, info.get("tag")),
                    "start_date": data.get("start_date"),
                }
            )
    rels = []
    if "relations" in index:
        start, end = index["relations"]
        for eid, text in iter_database_entries(melted, start, end):
            data = unwrap_entry(eid, text)
            first = as_dict(data.get("first"))
            second = as_dict(data.get("second"))
            a, b = _i(first.get("country")), _i(second.get("country"))
            if country_id not in {a, b}:
                continue
            other = b if a == country_id else a
            info = country_map.get(other or -1, {})
            rels.append(
                {
                    "other_id": other,
                    "other_tag": info.get("tag"),
                    "other_name": loc(info.get("dynamic_name"), lang, None) or loc(info.get("tag"), lang, info.get("tag")),
                    "relations": _num(data.get("relations")),
                    "obligation_us": bool(first.get("obligation")) if a == country_id else bool(second.get("obligation")),
                    "obligation_them": bool(second.get("obligation")) if a == country_id else bool(first.get("obligation")),
                }
            )
    rels.sort(key=lambda r: abs(r.get("relations") or 0), reverse=True)
    wars = []
    if "war_manager" in index:
        start, end = index["war_manager"]
        for eid, text in iter_database_entries(melted, start, end):
            data = unwrap_entry(eid, text)
            blob = str(data)
            if f"identity={country_id}" in blob or f"country={country_id}" in blob:
                wars.append({"id": eid, "summary": {k: data[k] for k in list(data)[:12] if not isinstance(data[k], (dict, list))}})
    return {"pacts": pacts, "relations": rels[:40], "wars": wars}


def extract_characters(melted, index, ids: list[int], country_id: int, lang: str) -> list[dict[str, Any]]:
    want = set(i for i in ids if i is not None)
    start, end = index["character_manager"]
    out = []
    for eid, text in iter_database_entries(melted, start, end):
        if want and eid not in want and len(out) > 30:
            # still scan for country politicians if specifically requested ids only
            if eid not in want:
                continue
        data = unwrap_entry(eid, text)
        if eid not in want and _i(data.get("country")) != country_id:
            continue
        if eid not in want:
            continue
        roles = as_list(as_dict(data.get("character_roles")).get("_values") or data.get("character_roles"))
        traits = as_list(as_dict(data.get("traits")).get("_values") or data.get("traits"))
        out.append(
            {
                "id": eid,
                "first_name": data.get("first_name"),
                "last_name": data.get("last_name"),
                "roles": roles,
                "ideology": data.get("ideology"),
                "ideology_name": loc(data.get("ideology"), lang, data.get("ideology")),
                "traits": [{"id": t, "name": loc(t, lang, t)} for t in traits],
                "birth_date": data.get("birth_date"),
                "culture_id": data.get("culture"),
                "interest_group_id": data.get("interest_group"),
                "popularity": data.get("popularity") or data.get("prominence"),
                "loyalty": data.get("loyalty"),
            }
        )
    return out


def extract_military(melted, index, country_id: int) -> dict[str, Any]:
    armies = []
    navies = []
    if "military_formation_manager" in index:
        start, end = index["military_formation_manager"]
        for eid, text in iter_database_entries(melted, start, end):
            data = unwrap_entry(eid, text)
            if _i(data.get("country")) != country_id:
                continue
            rec = {
                "id": eid,
                "type": data.get("type"),
                "name": data.get("name"),
                "organization": data.get("organization"),
                "supply": data.get("supply"),
                "home_hq": data.get("home_hq"),
                "mobilization_options": as_list(
                    as_dict(data.get("active_mobilization_options")).get("_values")
                    or data.get("active_mobilization_options")
                ),
            }
            if data.get("type") == "navy" or data.get("type") == "fleet":
                navies.append(rec)
            else:
                armies.append(rec)
    return {"armies": armies, "navies": navies, "army_count": len(armies), "navy_count": len(navies)}


def extract_states(melted, index, state_ids: set[int], lang: str) -> list[dict[str, Any]]:
    if not state_ids or "states" not in index:
        return []
    start, end = index["states"]
    out = []
    for eid, text in iter_database_entries(melted, start, end, skip_keys=SKIP_STATE_KEYS):
        if eid not in state_ids:
            continue
        data = unwrap_entry(eid, text)
        region = str(data.get("region") or "")
        pop = as_dict(data.get("pop_statistics"))
        out.append(
            {
                "id": eid,
                "region": region,
                "name": loc(region, lang, region),
                "incorporation": _num(data.get("incorporation")),
                "infrastructure": _num(data.get("infrastructure")),
                "infrastructure_usage": _num(data.get("infrastructure_usage")),
                "arable_land": data.get("arable_land"),
                "capital_province": data.get("capital"),
                "population": int(
                    (_num(pop.get("population_lower_strata"), 0) or 0)
                    + (_num(pop.get("population_middle_strata"), 0) or 0)
                    + (_num(pop.get("population_upper_strata"), 0) or 0)
                )
                if pop
                else None,
            }
        )
    out.sort(key=lambda s: s.get("population") or 0, reverse=True)
    return out


def extract_buildings(
    melted, index, state_ids: set[int], lang: str, *, top_n: int = 40
) -> dict[str, Any]:
    if not state_ids or "building_manager" not in index:
        return {"by_type": [], "unprofitable": [], "total_levels": 0}
    start, end = index["building_manager"]
    by_type: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"levels": 0, "count": 0, "profit": 0.0, "cash_reserves": 0.0, "states": set()}
    )
    unprofitable: list[dict[str, Any]] = []
    total = 0
    for eid, text in iter_database_entries(melted, start, end, skip_keys=SKIP_BUILDING_KEYS):
        data = unwrap_entry(eid, text)
        sid = _i(data.get("state"))
        if sid not in state_ids:
            continue
        btype = str(data.get("building") or "unknown")
        levels = int(_num(data.get("levels"), 0) or 0)
        profit = _num(data.get("profit_after_reserves"), 0) or 0
        cash = _num(data.get("cash_reserves"), 0) or 0
        rec = by_type[btype]
        rec["levels"] += levels
        rec["count"] += 1
        rec["profit"] += profit
        rec["cash_reserves"] += cash
        rec["states"].add(sid)
        total += levels
        if profit < -50 and levels > 0:
            unprofitable.append(
                {
                    "id": eid,
                    "building": btype,
                    "name": loc(btype, lang, btype),
                    "state_id": sid,
                    "levels": levels,
                    "profit": round(profit, 2),
                    "subsidized": bool(data.get("subsidized")),
                    "production_methods": as_list(
                        as_dict(data.get("production_methods")).get("_values") or data.get("production_methods")
                    ),
                }
            )
    rows = []
    for btype, rec in by_type.items():
        rows.append(
            {
                "building": btype,
                "name": loc(btype, lang, btype),
                "levels": rec["levels"],
                "count": rec["count"],
                "profit": round(rec["profit"], 2),
                "cash_reserves": round(rec["cash_reserves"], 2),
                "state_count": len(rec["states"]),
            }
        )
    rows.sort(key=lambda r: r["levels"], reverse=True)
    unprofitable.sort(key=lambda r: r["profit"])
    return {
        "total_levels": total,
        "types": len(rows),
        "by_type": rows[:top_n],
        "unprofitable": unprofitable[:25],
    }


def culture_lookup(melted, index) -> dict[int, str]:
    if "cultures" not in index:
        return {}
    start, end = index["cultures"]
    out: dict[int, str] = {}
    for eid, text in iter_database_entries(melted, start, end):
        data = unwrap_entry(eid, text)
        if data.get("type"):
            out[eid] = str(data["type"])
    return out


def resolve_cultures(pop_by_culture_id: dict[str, int], lookup: dict[int, str], lang: str) -> list[dict[str, Any]]:
    rows = []
    for k, n in pop_by_culture_id.items():
        try:
            cid = int(k)
        except ValueError:
            continue
        ident = lookup.get(cid, str(cid))
        rows.append({"id": cid, "culture": ident, "name": loc(ident, lang, ident), "population": n})
    rows.sort(key=lambda r: r["population"], reverse=True)
    return rows
