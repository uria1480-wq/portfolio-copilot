"""קבל הצעה: חוקים בקוד בלבד (proposal.py)."""
import ast
from datetime import date
from pathlib import Path

import pytest

from portfolio_copilot import proposal as proposal_module
from portfolio_copilot.proposal import (CORP_BONDS, GOV_BONDS, MONEY_MARKET, US_EQUITY, WORLD_EQUITY, build_proposal,
                                        equity_percent)
from portfolio_copilot.schemas import InvestorProfile

TODAY = date(2026, 11, 19)


def person(**extra):
    base = dict(age=35, recommended_risk_level="מאוזן", risk_confirmed=True, investment_horizon_years=10,
                marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=15000, monthly_expenses=10000,
                liquid_savings=80000, monthly_debt_payments=0, monthly_deposit=3000, pension_balance=100000,
                study_fund_balance=40000, other_assets=0)
    return InvestorProfile(**{**base, **extra})


def pct(p):
    return {line.asset_class: line.percent for line in p.capital.allocation}


# ---------- חוק 3: טבלת אחוז המניות ----------
@pytest.mark.parametrize("years, expected", [
    (1, (0, 10, 20)), (3, (0, 10, 20)),
    (4, (20, 40, 60)), (7, (20, 40, 60)),
    (8, (30, 55, 75)), (15, (30, 55, 75)),
    (16, (40, 65, 90)), (40, (40, 65, 90)),
])
def test_equity_table_by_horizon_and_risk(years, expected):
    for level, want in zip(("שמרני", "מאוזן", "אגרסיבי"), expected):
        assert equity_percent(level, years, age=20)[0] == want  # גיל 20: התקרה (90) לא משפיעה


# ---------- חוק 4: תקרת גיל ----------
def test_age_cap_limits_equity():
    p = build_proposal(person(age=50, recommended_risk_level="אגרסיבי", investment_horizon_years=20), TODAY)
    assert p.capital.equity_percent == 60  # 90 בטבלה, תקרה 110-50
    assert any("תקרת גיל" in r and "60" in r for r in p.reasons)


def test_age_cap_does_not_raise_equity():
    assert build_proposal(person(age=50, investment_horizon_years=5), TODAY).capital.equity_percent == 40


# ---------- חוק 5: חלוקת התמהיל ----------
def test_long_horizon_split():
    p = build_proposal(person(investment_horizon_years=10), TODAY)  # 55% מניות
    assert pct(p) == {US_EQUITY: 27.5, WORLD_EQUITY: 27.5, GOV_BONDS: 15.75, CORP_BONDS: 15.75, MONEY_MARKET: 13.5}


def test_short_horizon_split():
    p = build_proposal(person(investment_horizon_years=2), TODAY)  # 10% מניות, 90 לא-מניות
    assert pct(p) == {US_EQUITY: 5, WORLD_EQUITY: 5, GOV_BONDS: 18, CORP_BONDS: 18, MONEY_MARKET: 54}


@pytest.mark.parametrize("age", [20, 35, 47, 63, 80, 105])
@pytest.mark.parametrize("years", [1, 3, 5, 9, 15, 30])
@pytest.mark.parametrize("level", ["שמרני", "מאוזן", "אגרסיבי"])
def test_percent_always_sums_to_100(age, years, level):
    p = build_proposal(person(age=age, investment_horizon_years=years, recommended_risk_level=level), TODAY)
    assert round(sum(pct(p).values()), 6) == 100 and all(v >= 0 for v in pct(p).values())


# ---------- חוק 1: קרן חירום ----------
def test_emergency_six_months_with_surplus():
    p = build_proposal(person(), TODAY)  # רווק: 6 חודשים, 60,000. יש 80,000
    s = p.safety
    assert (s.emergency_target_months, s.emergency_target_amount, s.current_months, s.shortfall) == (6, 60000, 8.0, 0)
    assert s.months_to_fill is None and p.capital.liquid_surplus == 20000
    existing = {line.asset_class: line.existing_amount for line in p.capital.allocation}
    assert existing[US_EQUITY] == 5500 and round(sum(existing.values()), 2) == 20000


def test_emergency_three_months_for_salaried_with_earning_spouse():
    p = build_proposal(person(marital_status="נשוי", spouse_monthly_net_income=9000), TODAY)
    assert p.safety.emergency_target_months == 3 and p.safety.emergency_target_amount == 30000
    assert p.capital.liquid_surplus == 50000


@pytest.mark.parametrize("extra", [
    dict(marital_status="נשוי", spouse_monthly_net_income=0),
    dict(marital_status="ידוע בציבור", spouse_monthly_net_income=None),
    dict(marital_status="נשוי", spouse_monthly_net_income=9000, employment_status="עצמאי/ת"),
    dict(marital_status="גרוש", spouse_monthly_net_income=9000),
])
def test_emergency_stays_six_months_otherwise(extra):
    assert build_proposal(person(**extra), TODAY).safety.emergency_target_months == 6


def test_shortfall_goes_first_and_no_existing_capital_deployment():
    p = build_proposal(person(liquid_savings=35000), TODAY)  # יעד 60,000, חסר 25,000
    assert p.safety.shortfall == 25000 and p.safety.months_to_fill == 9  # 25,000 / 3,000 מעוגל למעלה
    assert any("קרן חירום" in s for s in p.safety.steps)
    assert p.capital.liquid_surplus == 0
    assert all(line.existing_amount is None for line in p.capital.allocation)
    monthly = {line.asset_class: line.monthly_amount for line in p.capital.allocation}
    assert round(sum(monthly.values()), 2) == 3000  # התמהיל חל על ההפקדה אחרי המילוי


# ---------- חוק 2: חובות ----------
def test_debt_above_limit_adds_step_without_changing_mix():
    base = build_proposal(person(), TODAY)
    p = build_proposal(person(monthly_debt_payments=5000), TODAY)  # 33%
    assert p.safety.reduce_debt_first and p.safety.debt_ratio == 0.333
    assert any("להקטין חוב לפני השקעה" in s for s in p.safety.steps)
    assert pct(p) == pct(base)


def test_debt_at_or_below_limit_has_no_step():
    p = build_proposal(person(monthly_debt_payments=4500), TODAY)  # 30% בדיוק
    assert not p.safety.reduce_debt_first and not any("חוב" in s for s in p.safety.steps)


# ---------- חוק 7: פנסיה והשתלמות ----------
def test_under_40_is_all_equity_regardless_of_table():
    p = build_proposal(person(age=39, recommended_risk_level="שמרני", investment_horizon_years=2), TODAY)
    assert (p.pension.pension_track, p.pension.study_fund_track) == ("100% מנייתי", "100% מנייתי")


@pytest.mark.parametrize("age, level, years, track", [
    (45, "מאוזן", 10, "כללי"),          # 55%
    (45, "שמרני", 10, 'אג"ח/שמרני'),    # 30%
    (45, "אגרסיבי", 20, "מנייתי"),      # 90% בטבלה. תקרת הגיל (65%) לא חלה על פנסיה
    (70, "אגרסיבי", 10, "כללי"),        # 75% בטבלה, תקרה 40% רק להון הנזיל
    (60, "מאוזן", 16, "כללי"),          # 65%
])
def test_from_40_track_follows_table_percent_without_age_cap(age, level, years, track):
    p = build_proposal(person(age=age, recommended_risk_level=level, investment_horizon_years=years), TODAY)
    assert p.pension.pension_track == track == p.pension.study_fund_track


def test_age_cap_applies_to_liquid_mix_but_not_to_pension():
    p = build_proposal(person(age=70, recommended_risk_level="אגרסיבי", investment_horizon_years=20), TODAY)
    assert p.capital.equity_percent == 40 and p.pension.pension_track == "מנייתי"
    assert any("בלי תקרת גיל" in r and "90%" in r for r in p.reasons)


def test_track_thresholds():
    track = proposal_module.pension_track
    assert (track(40, 80), track(40, 79.9), track(40, 40), track(40, 39.9)) == ("מנייתי", "כללי", "כללי", 'אג"ח/שמרני')
    assert track(39, 0) == "100% מנייתי"


# ---------- חוק 8: ריכוז בנכסים אחרים ----------
def test_other_assets_concentration_note():
    p = build_proposal(person(other_assets=220000), TODAY)  # 220 מתוך 440
    assert p.notes and "50%" in p.notes[0]
    assert pct(p) == pct(build_proposal(person(), TODAY))  # מידע בלבד


def test_no_concentration_note_below_threshold():
    assert build_proposal(person(other_assets=200000), TODAY).notes == []


# ---------- שדות חסרים ----------
@pytest.mark.parametrize("field", ["age", "recommended_risk_level", "investment_horizon_years"])
def test_missing_required_field_means_no_mix(field):
    p = build_proposal(person(**{field: None}), TODAY)
    assert field in p.missing and p.capital is None and p.pension is None
    assert p.safety is not None  # קרן חירום וחוב לא תלויים בשדות האלה


def test_unconfirmed_risk_means_no_mix():
    p = build_proposal(person(risk_confirmed=False), TODAY)
    assert "risk_confirmed" in p.missing and p.capital is None


def test_missing_other_fields_skip_only_their_part():
    p = build_proposal(person(monthly_expenses=None, monthly_deposit=None, monthly_net_income=None), TODAY)
    assert {"monthly_expenses", "monthly_deposit", "monthly_net_income"} <= set(p.missing)
    assert p.safety is None  # אין הוצאות ואין נטו: לא קרן חירום ולא יחס חוב
    assert p.capital is not None and p.capital.liquid_surplus is None and p.capital.monthly_deposit is None
    assert all(line.existing_amount is None and line.monthly_amount is None for line in p.capital.allocation)


def test_empty_profile_lists_missing_and_builds_nothing():
    p = build_proposal(InvestorProfile(), TODAY)
    assert p.safety is None and p.capital is None and p.pension is None
    assert {"age", "recommended_risk_level", "investment_horizon_years", "monthly_expenses"} <= set(p.missing)
    assert p.as_of == TODAY


# ---------- הסברים ----------
def test_reasons_cite_the_numbers():
    text = " ".join(build_proposal(person(), TODAY).reasons)
    assert "6 חודשי הוצאות" in text and "₪60,000" in text and "55%" in text and "₪20,000" in text


# ---------- בלי LLM ----------
def test_module_does_not_import_openai():
    tree = ast.parse(Path(proposal_module.__file__).read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "openai" not in imported and "portfolio_copilot.agent" not in {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}


# ---------- ממשק ----------
def test_full_profile_shows_three_sections_with_table_and_reasons():
    from portfolio_copilot.ui import proposal_html
    html = proposal_html(build_proposal(person(), TODAY))
    for title in ("1. ביטחון: קרן חירום וחובות", "2. ההון הקיים", "3. פנסיה והשתלמות", "על מה ההצעה מבוססת"):
        assert title in html
    assert "מדד מניות עולמי" in html and "27.5%" in html and "₪5,500" in html and "100% מנייתי" in html
    assert "מה חסר" not in html and "לא חושב" not in html


def test_partial_profile_shows_what_is_missing():
    from portfolio_copilot.ui import proposal_html
    html = proposal_html(build_proposal(InvestorProfile(age=30, monthly_expenses=8000), TODAY))
    assert "מה חסר כדי להשלים את ההצעה" in html and "אופק השקעה" in html and "רמת סיכון מוצעת" in html
    assert "לא חושב" in html


def test_proposal_text_is_escaped():
    from portfolio_copilot.ui import proposal_html
    from portfolio_copilot.proposal import Proposal
    evil = "<script>x</script>"
    html = proposal_html(Proposal(as_of=TODAY, missing=[evil], notes=[evil], reasons=[evil]))
    assert evil not in html and "&lt;script&gt;" in html


def test_app_handler_reads_saved_profile(monkeypatch):
    import os
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")
    from portfolio_copilot import app as appmod
    from portfolio_copilot.db import Store
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    assert "מה חסר" in appmod.make_proposal_handler(store, uid)()
    store.save_profile(uid, person())
    html = appmod.make_proposal_handler(store, uid)()
    assert "2. ההון הקיים" in html and "מה חסר" not in html


# ---------- allocate_monthly ----------
from portfolio_copilot.proposal import allocate_monthly  # noqa: E402


def total(r):
    return round(r.emergency_amount + sum(line.amount for line in r.lines or []) + r.unallocated, 2)


def test_shortfall_bigger_than_deposit_goes_all_to_emergency():
    r = allocate_monthly(person(liquid_savings=35000), 3000, TODAY)  # חסרים 25,000
    assert r.emergency_amount == 3000 and r.lines == [] and total(r) == 3000
    assert any("לכספית" in x for x in r.reasons)


def test_partial_shortfall_then_mix():
    r = allocate_monthly(person(liquid_savings=59000), 3000, TODAY)  # חסרים 1,000
    amounts = {line.asset_class: line.amount for line in r.lines}
    assert r.emergency_amount == 1000 and round(sum(amounts.values()), 2) == 2000
    assert amounts[US_EQUITY] == 550 and total(r) == 3000


def test_no_shortfall_all_by_mix_long_horizon():
    r = allocate_monthly(person(), 10000, TODAY)  # 55% מניות, אופק 10
    amounts = {line.asset_class: line.amount for line in r.lines}
    assert r.emergency_amount == 0
    assert amounts == {US_EQUITY: 2750, WORLD_EQUITY: 2750, GOV_BONDS: 1575, CORP_BONDS: 1575, MONEY_MARKET: 1350}


def test_short_horizon_mix():
    r = allocate_monthly(person(investment_horizon_years=2), 10000, TODAY)  # 10% מניות
    amounts = {line.asset_class: line.amount for line in r.lines}
    assert amounts == {US_EQUITY: 500, WORLD_EQUITY: 500, GOV_BONDS: 1800, CORP_BONDS: 1800, MONEY_MARKET: 5400}


@pytest.mark.parametrize("deposit", [1, 99.99, 1234.57, 3333.33, 10000, 77777.77])
@pytest.mark.parametrize("liquid", [0, 59999.5, 80000])
def test_amounts_always_sum_to_the_deposit(deposit, liquid):
    r = allocate_monthly(person(liquid_savings=liquid), deposit, TODAY)
    assert total(r) == round(deposit, 2) and all(line.amount >= 0 for line in r.lines)


@pytest.mark.parametrize("field", ["age", "recommended_risk_level", "investment_horizon_years"])
def test_missing_profile_gives_emergency_only(field):
    r = allocate_monthly(person(liquid_savings=59000, **{field: None}), 3000, TODAY)
    assert field in r.missing and r.lines is None
    assert r.emergency_amount == 1000 and r.unallocated == 2000 and total(r) == 3000


def test_unconfirmed_risk_gives_emergency_only():
    r = allocate_monthly(person(risk_confirmed=False), 3000, TODAY)
    assert "risk_confirmed" in r.missing and r.lines is None and r.unallocated == 3000


def test_unknown_expenses_skip_emergency_and_are_listed():
    r = allocate_monthly(person(monthly_expenses=None), 3000, TODAY)
    assert "monthly_expenses" in r.missing and r.emergency_amount == 0 and total(r) == 3000


def test_deposit_must_be_positive():
    for bad in (0, -5, None):
        with pytest.raises(ValueError):
            allocate_monthly(person(), bad, TODAY)


# ---------- monthly_report ----------
from portfolio_copilot.proposal import monthly_report  # noqa: E402


def test_monthly_report_fixed_and_percent():
    fixed = monthly_report(person(), 20000, 2000, 800, "fixed", 3000, TODAY)
    assert (fixed.period, fixed.set_aside, fixed.free_to_spend, fixed.total_saved_this_month) == ("2026-11", 3000, 17000, 5800)
    pct = monthly_report(person(), 20000, None, None, "percent", 15, TODAY)
    assert pct.set_aside == 3000 and pct.pension_contributions == 0 and "15%" in pct.allocation.reasons[0]


@pytest.mark.parametrize("args, message", [
    ((0, None, None, "fixed", 100), "נטו"),
    ((1000, -1, None, "fixed", 100), "שליליות"),
    ((1000, None, None, "fixed", 0), "כמה להשקיע"),
    ((1000, None, None, "percent", 120), "100%"),
    ((1000, None, None, "fixed", 2000), "גבוה מהנטו"),
    ((1000, None, None, "other", 100), "לא מוכר"),
])
def test_monthly_report_rejects_bad_input(args, message):
    with pytest.raises(ValueError, match=message):
        monthly_report(person(), *args, today=TODAY)
