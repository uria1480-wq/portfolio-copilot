from portfolio_copilot.agent_tools import run_tool
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile, merge_profile

PRICES = {"VT": 100.0, "BND": 50.0, "ZIM": 20.0}
fetch = lambda s: PRICES[s]


def setup():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    s.upsert_holding(uid, "VT", 10)
    s.upsert_holding(uid, "BND", 10)
    return s, uid


def approved(**extra):
    return merge_profile(InvestorProfile(), {"age": 30, "recommended_risk_level": "מאוזן", "risk_confirmed": True,
                                             "investment_horizon_years": 15, **extra})


def test_get_portfolio_values_and_weights():
    s, uid = setup()
    r = run_tool("get_portfolio", {}, s, uid, InvestorProfile(), fetch)
    assert r["total_value"] == 1500 and r["price_errors"] == []
    assert {h["symbol"]: h["weight"] for h in r["holdings"]} == {"VT": 0.6667, "BND": 0.3333}


def test_get_portfolio_reports_missing_prices_instead_of_failing():
    s, uid = setup()
    def flaky(sym):
        if sym == "BND":
            raise ValueError("no price")
        return 100.0
    r = run_tool("get_portfolio", {}, s, uid, InvestorProfile(), flaky)
    assert r["price_errors"] == ["BND"] and r["total_value"] == 1000


def test_get_portfolio_empty():
    s = Store(":memory:")
    r = run_tool("get_portfolio", {}, s, s.get_or_create_user("demo"), InvestorProfile(), fetch)
    assert r["holdings"] == []


def test_plan_deposit_uses_amount_and_splits_all_of_it():
    s, uid = setup()
    r = run_tool("plan_deposit", {"amount": 1000}, s, uid, approved(), fetch)
    assert "error" not in r and abs(sum(r["buys"].values()) - 1000) < 0.01 and r["sells"] == []


def test_plan_deposit_defaults_to_profile_monthly_deposit():
    s, uid = setup()
    r = run_tool("plan_deposit", {}, s, uid, approved(monthly_deposit=2000), fetch)
    assert r["deposit"] == 2000


def test_plan_deposit_errors_are_returned_not_raised():
    s, uid = setup()
    assert "סכום" in run_tool("plan_deposit", {}, s, uid, approved(), fetch)["error"]
    unapproved = InvestorProfile(age=30, recommended_risk_level="מאוזן")
    assert "error" in run_tool("plan_deposit", {"amount": 500}, s, uid, unapproved, fetch)
    assert "error" in run_tool("nope", {}, s, uid, approved(), fetch)


def test_rebalance_with_sell_and_keep_symbols():
    s, uid = setup()
    s.upsert_holding(uid, "ZIM", 4500)  # 90,000 מול 1,500 בשאר התיק
    p = approved(max_single_asset_weight=0.20)
    r = run_tool("plan_deposit", {"amount": 0, "allow_sell": True}, s, uid, p, fetch)
    assert [x["symbol"] for x in r["sells"]] == ["ZIM"] and not r["cap_breached"]
    kept = run_tool("plan_deposit", {"amount": 0, "allow_sell": True, "keep_symbols": ["ZIM"]}, s, uid, p, fetch)
    assert kept["sells"] == [] and kept["cap_breached"]