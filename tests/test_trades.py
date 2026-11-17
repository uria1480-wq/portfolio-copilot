import pytest
from portfolio_copilot.schemas import InvestorProfile, merge_profile
from portfolio_copilot.tools import plan_trades

PRICES = {"ZIM": 20.0, "VT": 100.0, "BND": 80.0, "BIL": 90.0}
CONCENTRATED = [{"symbol": "ZIM", "quantity": 4500, "avg_cost": 20.0},   # 90,000
                {"symbol": "VT", "quantity": 100, "avg_cost": 100.0}]    # 10,000


def profile(risk="אגרסיבי", cap=0.20):
    return merge_profile(InvestorProfile(), {
        "age": 30, "recommended_risk_level": risk, "risk_confirmed": True,
        "investment_horizon_years": 20, "max_single_asset_weight": cap})


def test_sells_concentrated_asset_down_to_cap_and_reinvests():
    r = plan_trades(profile(), CONCENTRATED, PRICES, deposit=0, allow_sell=True)
    assert r["sells"][0]["symbol"] == "ZIM"
    assert r["sells"][0]["amount"] == pytest.approx(70_000, rel=1e-5)
    assert sum(r["buys"].values()) == pytest.approx(70_000, rel=1e-5)
    assert r["weights_after"]["ZIM"] == pytest.approx(0.20, abs=1e-4)
    assert not r["cap_breached"]


def test_kept_symbol_is_never_sold_and_is_flagged():
    r = plan_trades(profile(), CONCENTRATED, PRICES, deposit=0, keep_symbols=["zim"], allow_sell=True)
    assert r["sells"] == [] and r["kept_symbols"] == ["ZIM"]
    assert r["cap_breached"] and "ZIM" in r["breaching_symbols"]


def test_no_sells_unless_allowed():
    r = plan_trades(profile(), CONCENTRATED, PRICES, deposit=5_000, allow_sell=False)
    assert r["sells"] == [] and r["cash_from_sales"] == 0
    assert sum(r["buys"].values()) == pytest.approx(5_000)
    assert "ZIM" not in r["buys"]


def test_cap_applies_to_single_assets_not_to_template_funds():
    r = plan_trades(profile("מאוזן"), [], PRICES, deposit=10_000)
    assert r["weights_after"]["VT"] == pytest.approx(0.60, abs=0.01)
    assert not r["cap_breached"]


def test_cap_is_measured_on_total_including_new_deposit():
    holdings = [{"symbol": "ZIM", "quantity": 1000, "avg_cost": 20.0}]   # 20,000
    r = plan_trades(profile(cap=0.20), holdings, PRICES, deposit=80_000, allow_sell=True)  # total 100,000
    assert r["sells"] == []  # 20% בדיוק, אין חריגה


def test_errors():
    with pytest.raises(ValueError, match="אין החזקות"):
        plan_trades(profile(), [], PRICES, deposit=0)
    with pytest.raises(ValueError, match="שלילי"):
        plan_trades(profile(), [], PRICES, deposit=-1)
    with pytest.raises(ValueError, match="טרם מאושר"):
        plan_trades(InvestorProfile(age=30), [], PRICES, deposit=100)