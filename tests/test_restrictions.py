"""חוק 6: "אל תקנה X" על סוג נכס משנה את ההצעה ואת החלוקה החודשית. סמל ספציפי רק נשמר."""
from datetime import date

import pytest

from portfolio_copilot.agent_tools import run_profile_tool, run_tool
from portfolio_copilot.db import Store
from portfolio_copilot.proposal import (ASSET_CLASSES, CORP_BONDS, GOV_BONDS, MONEY_MARKET, US_EQUITY, WORLD_EQUITY,
                                        allocate_monthly, asset_class_of, build_proposal)
from portfolio_copilot.schemas import InvestorProfile

TODAY = date(2026, 11, 22)
# בלי הגבלות: מאוזן, אופק 10, גיל 35 -> מניות 55% (27.5 + 27.5), אג"ח 31.5% (15.75 + 15.75), כספית 13.5%
BASE = {US_EQUITY: 27.5, WORLD_EQUITY: 27.5, GOV_BONDS: 15.75, CORP_BONDS: 15.75, MONEY_MARKET: 13.5}


def person(*no_buy, **extra):
    base = dict(age=35, recommended_risk_level="מאוזן", risk_confirmed=True, investment_horizon_years=10,
                marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=15000, monthly_expenses=10000,
                liquid_savings=80000, monthly_debt_payments=0, monthly_deposit=3000, pension_balance=100000,
                study_fund_balance=40000, other_assets=0, no_buy_symbols=list(no_buy))
    return InvestorProfile(**{**base, **extra})


def mix(profile):
    return {line.asset_class: line.percent for line in build_proposal(profile, TODAY).capital.allocation}


def monthly(profile, amount=3000, already=0.0):
    r = allocate_monthly(profile, amount, TODAY, already)
    return r, {line.asset_class: line.amount for line in r.lines}


def test_no_restriction_keeps_base_mix():
    assert mix(person()) == BASE


@pytest.mark.parametrize("blocked, target", [
    (CORP_BONDS, GOV_BONDS),
    (GOV_BONDS, CORP_BONDS),
    (US_EQUITY, WORLD_EQUITY),
    (WORLD_EQUITY, US_EQUITY),
    (MONEY_MARKET, GOV_BONDS),
])
def test_each_asset_class_moves_to_its_neighbor(blocked, target):
    p = person(blocked)
    m = mix(p)
    assert m[blocked] == 0 and m[target] == BASE[target] + BASE[blocked]
    assert round(sum(m.values()), 2) == 100
    assert any(f"לא לקנות {blocked}" in r and target in r for r in build_proposal(p, TODAY).reasons)
    _, amounts = monthly(p)
    assert amounts[blocked] == 0 and round(sum(amounts.values()), 2) == 3000


@pytest.mark.parametrize("group, other", [
    ((US_EQUITY, WORLD_EQUITY), BASE[US_EQUITY] + BASE[WORLD_EQUITY]),
    ((GOV_BONDS, CORP_BONDS), BASE[GOV_BONDS] + BASE[CORP_BONDS]),
])
def test_whole_group_blocked_goes_to_money_market(group, other):
    m = mix(person(*group))
    assert all(m[k] == 0 for k in group) and m[MONEY_MARKET] == BASE[MONEY_MARKET] + other
    assert round(sum(m.values()), 2) == 100


def test_equity_percent_reflects_final_mix():
    assert build_proposal(person(US_EQUITY, WORLD_EQUITY), TODAY).capital.equity_percent == 0
    assert build_proposal(person(US_EQUITY), TODAY).capital.equity_percent == 55


def test_money_market_and_gov_blocked_goes_to_corp():
    m = mix(person(MONEY_MARKET, GOV_BONDS))
    assert m[MONEY_MARKET] == m[GOV_BONDS] == 0 and m[CORP_BONDS] == 15.75 + 15.75 + 13.5
    assert round(sum(m.values()), 2) == 100


def test_all_bonds_and_money_market_blocked_stays_and_explains():
    """אין חלופה מותרת שאינה מניות: החלקים נשארים, עם הסבר, והסכום עדיין 100%."""
    p = person(GOV_BONDS, CORP_BONDS, MONEY_MARKET)
    m = mix(p)
    assert round(sum(m.values()), 2) == 100 and m[US_EQUITY] == 27.5
    assert any("כל החלופות שלו אסורות" in r for r in build_proposal(p, TODAY).reasons)


def test_duplicate_restriction_is_counted_once():
    assert mix(person(CORP_BONDS, CORP_BONDS)) == mix(person(CORP_BONDS))


@pytest.mark.parametrize("blocked", [(), *[(k,) for k in ASSET_CLASSES],
                                     (US_EQUITY, CORP_BONDS), (WORLD_EQUITY, MONEY_MARKET),
                                     (US_EQUITY, WORLD_EQUITY, GOV_BONDS, CORP_BONDS)])
@pytest.mark.parametrize("risk, years", [("שמרני", 2), ("מאוזן", 10), ("אגרסיבי", 30)])
def test_mix_always_sums_to_100_and_monthly_to_deposit(blocked, risk, years):
    p = person(*blocked, recommended_risk_level=risk, investment_horizon_years=years)
    assert round(sum(mix(p).values()), 2) == 100
    _, amounts = monthly(p, 1234.57)
    assert round(sum(amounts.values()), 2) == 1234.57
    assert all(amounts[k] == 0 for k in blocked if mix(p)[k] == 0)


def test_unknown_symbol_does_not_change_anything():
    p = person("TSLA", "XYZ123")
    assert build_proposal(p, TODAY).capital == build_proposal(person(), TODAY).capital
    assert monthly(p)[1] == monthly(person())[1]


def test_emergency_fund_goes_to_gov_bonds_when_money_market_blocked():
    p = person(MONEY_MARKET, liquid_savings=30000)  # חוסר 30,000
    r, _ = monthly(p)
    assert r.emergency_amount == 3000 and r.emergency_asset_class == GOV_BONDS
    assert any(f"קודם ל{GOV_BONDS}" in x for x in r.reasons)
    assert GOV_BONDS in build_proposal(p, TODAY).safety.steps[0]
    assert monthly(person(liquid_savings=30000))[0].emergency_asset_class == MONEY_MARKET


@pytest.mark.parametrize("text, expected", [
    ('אג"ח קונצרני', CORP_BONDS), ("אג״ח  קונצרני", CORP_BONDS), (" כספית ", MONEY_MARKET),
    ("קרן כספית", MONEY_MARKET), ('מניות ארה"ב', US_EQUITY), ("s&p 500", US_EQUITY),
    ("מניות עולמיות", WORLD_EQUITY), ("msci world", WORLD_EQUITY), ("אגרות חוב ממשלתיות", GOV_BONDS),
])
def test_asset_class_name_and_aliases_are_normalized(text, expected):
    assert asset_class_of(text) == expected


@pytest.mark.parametrize("text", ["TSLA", "מניות", 'אג"ח', "קרן השתלמות", ""])
def test_unrecognized_text_is_not_an_asset_class(text):
    assert asset_class_of(text) is None


def test_alias_restriction_is_saved_under_canonical_name():
    result, p = run_profile_tool("add_restriction", {"item": "קרן כספית"}, person())
    assert result["asset_class"] == MONEY_MARKET and p.no_buy_symbols == [MONEY_MARKET]
    assert mix(p)[MONEY_MARKET] == 0


# ---------- הכלי של הסוכן ----------
def test_add_restriction_on_asset_class_affects_proposal():
    result, p = run_profile_tool("add_restriction", {"item": "אג״ח קונצרני"}, person())
    assert result["affects_proposal"] and result["asset_class"] == CORP_BONDS and "note" not in result
    assert p.no_buy_symbols == [CORP_BONDS]
    s = Store(":memory:")
    after = run_tool("get_proposal", {}, s, s.get_or_create_user("demo"), p, TODAY)
    assert {line["asset_class"]: line["percent"] for line in after["capital"]["allocation"]}[CORP_BONDS] == 0


def test_add_restriction_on_symbol_is_saved_but_says_it_does_not_affect():
    result, p = run_profile_tool("add_restriction", {"item": "tsla"}, person())
    assert result["saved"] and not result["affects_proposal"] and result["asset_class"] is None
    assert "סוגי נכסים" in result["note"] and p.no_buy_symbols == ["TSLA"]


# ---------- הסרת הגבלה ----------
def test_remove_asset_class_restriction_restores_mix():
    _, p = run_profile_tool("add_restriction", {"item": CORP_BONDS}, person())
    _, p = run_profile_tool("add_restriction", {"item": "TSLA"}, p)
    result, p = run_profile_tool("remove_restriction", {"item": "אג\"ח קונצרניות"}, p)  # גם בניסוח אחר
    assert result["removed"] == CORP_BONDS and result["affects_proposal"]
    assert p.no_buy_symbols == ["TSLA"] and p.restrictions == ["לא לקנות: TSLA"]
    assert mix(p) == BASE


def test_remove_symbol_restriction():
    _, p = run_profile_tool("add_restriction", {"item": "TSLA"}, person())
    result, p = run_profile_tool("remove_restriction", {"item": "tsla"}, p)
    assert result["removed"] == "TSLA" and not result["affects_proposal"] and p.no_buy_symbols == []


@pytest.mark.parametrize("args", [{"item": "NVDA"}, {"item": ""}, {}])
def test_remove_unknown_restriction_is_an_error_and_keeps_profile(args):
    _, p = run_profile_tool("add_restriction", {"item": "TSLA"}, person())
    result, same = run_profile_tool("remove_restriction", args, p)
    assert "error" in result and same == p and result["no_buy_symbols"] == ["TSLA"]


def test_free_text_restrictions_are_kept_when_removing():
    p = person("TSLA", restrictions=["לא לקנות: TSLA", "בלי נשק"])
    _, p = run_profile_tool("remove_restriction", {"item": "TSLA"}, p)
    assert p.restrictions == ["בלי נשק"]


# ---------- קבוצה שלמה: "מניות" / "אג"ח" ----------
@pytest.mark.parametrize("text, group", [("מניות", (US_EQUITY, WORLD_EQUITY)), ("שוק המניות", (US_EQUITY, WORLD_EQUITY)),
                                         ('אג"ח', (GOV_BONDS, CORP_BONDS)), ("אג״ח", (GOV_BONDS, CORP_BONDS)),
                                         ("אגרות חוב", (GOV_BONDS, CORP_BONDS))])
def test_group_restriction_blocks_whole_group(text, group):
    result, p = run_profile_tool("add_restriction", {"item": text}, person())
    assert result["affects_proposal"] and result["blocked_asset_classes"] == list(group)
    m = mix(p)
    assert all(m[k] == 0 for k in group) and m[MONEY_MARKET] == BASE[MONEY_MARKET] + sum(BASE[k] for k in group)
    assert round(sum(m.values()), 2) == 100
    _, amounts = monthly(p)
    assert all(amounts[k] == 0 for k in group) and round(sum(amounts.values()), 2) == 3000


def test_group_restriction_is_saved_canonically_and_removable():
    _, p = run_profile_tool("add_restriction", {"item": "אגרות חוב"}, person())
    assert p.no_buy_symbols == ['אג"ח'] and p.restrictions == ['לא לקנות: אג"ח']
    result, p = run_profile_tool("remove_restriction", {"item": "אג״ח"}, p)
    assert result["removed"] == 'אג"ח' and p.no_buy_symbols == [] and mix(p) == BASE


def test_group_plus_class_restriction_counts_each_class_once():
    assert mix(person("מניות", US_EQUITY)) == mix(person("מניות"))


def test_symbol_result_has_no_blocked_classes():
    result, _ = run_profile_tool("add_restriction", {"item": "TSLA"}, person())
    assert result["blocked_asset_classes"] == [] and not result["affects_proposal"]


# ---------- פרופיל ישן: "לא למכור" ----------
def test_legacy_no_sell_restrictions_are_dropped_and_others_kept():
    p = InvestorProfile.model_validate_json(
        '{"restrictions": ["לא למכור: ZIM", "בלי נשק", "לא לקנות: TSLA"], "no_buy_symbols": ["TSLA"]}')
    assert p.restrictions == ["בלי נשק", "לא לקנות: TSLA"]
