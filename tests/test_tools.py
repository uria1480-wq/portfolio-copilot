import pytest
from portfolio_copilot.schemas import InvestorProfile, merge_profile
from portfolio_copilot.tools import parse_holdings_csv, get_prices, allocate_deposit

PRICES = {"ZIM": 20.0, "VT": 100.0, "BND": 80.0, "BIL": 90.0}


def profile(risk="אגרסיבי", cap=0.20):
    return merge_profile(InvestorProfile(), {
        "age": 30, "recommended_risk_level": risk, "risk_confirmed": True,
        "investment_horizon_years": 20, "max_single_asset_weight": cap})


def test_parse_csv_ok():
    rows = parse_holdings_csv("symbol,quantity,avg_cost\nzim,100,18.5\nVT,5,\n")
    assert rows == [{"symbol": "ZIM", "quantity": 100.0, "avg_cost": 18.5},
                    {"symbol": "VT", "quantity": 5.0, "avg_cost": None}]


def test_parse_csv_errors_are_clear():
    with pytest.raises(ValueError, match="שורה 2"):
        parse_holdings_csv("symbol,quantity\nZIM,abc\n")
    with pytest.raises(ValueError, match="חסרות עמודות"):
        parse_holdings_csv("ticker,amount\nZIM,1\n")


def test_get_prices_uses_injected_fetcher():
    assert get_prices(["A", "B"], fetch=lambda s: 10.0) == {"A": 10.0, "B": 10.0}


def test_empty_portfolio_follows_risk_template():
    r = allocate_deposit(profile("מאוזן"), [], PRICES, 10_000)
    assert sum(r["deposit_split"].values()) == pytest.approx(10_000)
    assert r["weights_after"]["VT"] == pytest.approx(0.60, abs=0.01)
    assert r["weights_after"]["BND"] == pytest.approx(0.30, abs=0.01)


def test_concentrated_holding_is_not_sold_and_gets_no_new_money():
    holdings = [{"symbol": "ZIM", "quantity": 4500, "avg_cost": 20.0}]  # 90,000
    holdings.append({"symbol": "VT", "quantity": 100, "avg_cost": 100.0})  # 10,000
    r = allocate_deposit(profile(), holdings, PRICES, 10_000)
    assert "ZIM" not in r["deposit_split"]
    assert r["weights_after"]["ZIM"] < r["weights_before"]["ZIM"]
    assert r["cap_breached"] and "ZIM" in r["breaching_symbols"]


def test_unconfirmed_profile_is_rejected():
    p = InvestorProfile(age=30, recommended_risk_level="מאוזן", investment_horizon_years=10)
    with pytest.raises(ValueError, match="טרם מאושר"):
        allocate_deposit(p, [], PRICES, 1000)


def test_missing_price_and_bad_deposit():
    with pytest.raises(ValueError, match="חסרים מחירים"):
        allocate_deposit(profile(), [{"symbol": "XYZ", "quantity": 1, "avg_cost": None}], PRICES, 1000)
    with pytest.raises(ValueError, match="חיובי"):
        allocate_deposit(profile(), [], PRICES, 0)