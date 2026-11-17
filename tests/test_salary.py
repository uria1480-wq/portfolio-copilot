import pytest

from portfolio_copilot.agent_tools import run_tool
from portfolio_copilot.db import Store
from portfolio_copilot.plan import Bucket, SavingsPlan
from portfolio_copilot.salary import plan_salary
from portfolio_copilot.schemas import InvestorProfile, merge_profile

PRICES = {"ZIM": 20.0, "VT": 100.0, "BND": 80.0, "BIL": 90.0}
fetch = lambda s: PRICES[s]


def approved(**extra):
    return merge_profile(InvestorProfile(), {"age": 35, "recommended_risk_level": "מאוזן", "risk_confirmed": True,
                                             "investment_horizon_years": 20, **extra})


def plan(mode="fixed", value=10_000, cash=0.3, confirmed=True, cash_name="קרן חירום"):
    buckets = [Bucket(name="השקעות", kind="invest", share=1 - cash)]
    if cash:
        buckets.insert(0, Bucket(name=cash_name, kind="cash", share=cash))
    return SavingsPlan(savings_mode=mode, savings_value=value, buckets=buckets, confirmed=confirmed)


# ---- המודל ----
def test_percent_can_be_entered_as_whole_number():
    assert SavingsPlan(savings_mode="percent", savings_value=25).savings_value == 0.25
    with pytest.raises(ValueError):
        SavingsPlan(savings_mode="percent", savings_value=250)


def test_bucket_shares_are_normalized_and_readiness_needs_confirmation():
    p = SavingsPlan(savings_value=100, buckets=[Bucket(name="a", kind="cash", share=0.3), Bucket(name="b", kind="invest", share=0.3)])
    assert [b.share for b in p.buckets] == [0.5, 0.5] and not p.is_ready()
    assert p.model_copy(update={"confirmed": True}).is_ready()


# ---- המנוע: אותו קוד, אנשים שונים ----
def test_high_earner_gets_a_plan_scaled_to_his_income():
    r = plan_salary(approved(), plan(value=10_000, cash=0.3), [], PRICES, net=40_000, pension=4_000, study_fund=2_500)
    assert r["set_aside"] == 10_000 and r["free_to_spend"] == 30_000
    assert r["total_saved_this_month"] == 16_500
    transfers = [a for a in r["actions"] if a["type"] == "transfer"]
    buys = [a for a in r["actions"] if a["type"] == "buy"]
    assert transfers == [{"type": "transfer", "bucket": "קרן חירום", "amount": 3_000.0}]
    assert sum(a["amount"] for a in buys) == pytest.approx(7_000)


def test_teenager_with_small_income_gets_a_different_outcome_from_the_same_engine():
    teen_plan = plan(mode="percent", value=10, cash=1.0, cash_name="חיסכון לטיול")
    r = plan_salary(InvestorProfile(age=16), teen_plan, [], {}, net=4_000)  # בלי השקעות, הפרופיל לא נדרש
    assert r["set_aside"] == 400 and r["free_to_spend"] == 3_600
    assert r["actions"] == [{"type": "transfer", "bucket": "חיסכון לטיול", "amount": 400.0}]


def test_actions_always_add_up_to_the_amount_set_aside():
    r = plan_salary(approved(), plan(mode="percent", value=0.333, cash=1 / 3), [], PRICES, net=1_001)
    assert sum(a["amount"] for a in r["actions"]) == pytest.approx(r["set_aside"], abs=0.01)


def test_planned_amount_above_net_is_capped_with_a_warning():
    r = plan_salary(approved(), plan(value=10_000, cash=0), [], PRICES, net=4_000)
    assert r["set_aside"] == 4_000 and r["free_to_spend"] == 0 and r["warnings"]


def test_concentration_is_reported_but_nothing_is_sold():
    holdings = [{"symbol": "ZIM", "quantity": 4500, "avg_cost": 20.0}]
    r = plan_salary(approved(max_single_asset_weight=0.2), plan(value=1_000, cash=0), holdings, PRICES, net=20_000)
    assert r["cap_breached"] and "ZIM" in r["breaching_symbols"]
    assert all(a["type"] != "sell" for a in r["actions"])


def test_engine_refuses_when_not_ready():
    with pytest.raises(ValueError, match="טרם אושרה"):
        plan_salary(approved(), plan(confirmed=False), [], PRICES, net=10_000)
    with pytest.raises(ValueError, match="חיובי"):
        plan_salary(approved(), plan(), [], PRICES, net=0)
    with pytest.raises(ValueError, match="טרם מאושר"):
        plan_salary(InvestorProfile(age=30), plan(), [], PRICES, net=10_000)


# ---- מסד הנתונים ----
def test_plan_and_events_are_stored_per_user():
    s = Store(":memory:")
    a, b = s.get_or_create_user("a"), s.get_or_create_user("b")
    assert s.load_plan(a) == SavingsPlan()
    s.save_plan(a, plan())
    assert s.load_plan(a).is_ready() and not s.load_plan(b).savings_value
    for net in (1000.0, 2000.0):
        s.add_salary_event(a, {"period": "2026-11", "net": net, "set_aside": 1.0, "actions": []})
    assert [e["net"] for e in s.list_salary_events(a)] == [2000.0, 1000.0] and s.list_salary_events(b) == []


# ---- כלים של הסוכן ----
def setup_store(with_payslip=True):
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    if with_payslip:
        s.save_document(uid, {"doc_type": "payslip", "period": "2026-10", "data": {}, "warnings": [],
                              "summary": {"period": "2026-10", "net_to_bank": 12_000.0,
                                          "pension_monthly_total": 2_000.0, "study_fund_monthly_total": 800.0}})
    return s, uid


def test_propose_plan_needs_explicit_confirmation_and_resets_on_change():
    s, uid = setup_store(False)
    r = run_tool("propose_plan", {"savings_mode": "fixed", "savings_value": 3000}, s, uid, InvestorProfile())
    assert r["saved"] and not r["ready_to_run"]
    r = run_tool("propose_plan", {"user_confirmed": True}, s, uid, InvestorProfile())  # רק אישור, שאר השדות נשמרים
    assert r["ready_to_run"] and r["plan"]["savings_value"] == 3000
    r = run_tool("propose_plan", {"savings_value": 4000}, s, uid, InvestorProfile())  # שינוי בלי אישור חדש
    assert not r["ready_to_run"]
    assert "error" in run_tool("propose_plan", {"savings_mode": "percent", "savings_value": 500}, s, uid, InvestorProfile())


def test_salary_received_defaults_to_latest_payslip_and_records_the_event():
    s, uid = setup_store()
    run_tool("propose_plan", {"savings_mode": "fixed", "savings_value": 3000, "user_confirmed": True,
                              "buckets": [{"name": "קרן חירום", "kind": "cash", "share": 1.0}]}, s, uid, approved())
    r = run_tool("salary_received", {}, s, uid, approved(), fetch)
    assert r["net"] == 12_000 and r["pension_contributions"] == 2_000 and r["study_fund_contributions"] == 800
    assert len(s.list_salary_events(uid)) == 1


def test_salary_received_errors_are_explained_not_raised():
    s, uid = setup_store(False)
    assert "נטו" in run_tool("salary_received", {}, s, uid, approved(), fetch)["error"]
    assert "טרם אושרה" in run_tool("salary_received", {"net": 9000}, s, uid, approved(), fetch)["error"]