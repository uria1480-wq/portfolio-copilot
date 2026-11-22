"""הכלים של "שאל את הסוכן": get_proposal ו-get_monthly_allocation מחזירים את מה שהקוד מחשב (proposal.py)."""
from datetime import date

from portfolio_copilot.agent_tools import run_tool
from portfolio_copilot.db import Store
from portfolio_copilot.proposal import allocate_monthly, build_proposal
from portfolio_copilot.schemas import InvestorProfile

TODAY = date(2026, 11, 22)


def setup():
    s = Store(":memory:")
    return s, s.get_or_create_user("demo")


def approved(**extra):
    return InvestorProfile(**{"age": 30, "recommended_risk_level": "מאוזן", "risk_confirmed": True,
                              "investment_horizon_years": 15, "marital_status": "רווק", "employment_status": "שכיר/ה",
                              "monthly_net_income": 20000, "monthly_expenses": 10000, "liquid_savings": 30000,
                              "monthly_debt_payments": 0, "monthly_deposit": 4000, **extra})


def test_get_proposal_returns_build_proposal():
    s, uid = setup()
    r = run_tool("get_proposal", {}, s, uid, approved(), TODAY)
    assert r == build_proposal(approved(), TODAY).model_dump(mode="json")
    assert r["capital"]["allocation"] and r["safety"]["shortfall"] == 30000  # יעד 6 חודשים = 60,000


def test_get_proposal_reports_missing_fields_instead_of_guessing():
    s, uid = setup()
    r = run_tool("get_proposal", {}, s, uid, InvestorProfile(), TODAY)
    assert r["capital"] is None and "age" in r["missing"]


def test_get_monthly_allocation_uses_amount():
    s, uid = setup()
    r = run_tool("get_monthly_allocation", {"amount": 2000}, s, uid, approved(liquid_savings=100000), TODAY)
    assert r == allocate_monthly(approved(liquid_savings=100000), 2000, TODAY).model_dump(mode="json")
    assert r["emergency_amount"] == 0 and round(sum(line["amount"] for line in r["lines"]), 2) == 2000


def test_get_monthly_allocation_defaults_to_profile_deposit():
    s, uid = setup()
    r = run_tool("get_monthly_allocation", {}, s, uid, approved(), TODAY)
    assert r["deposit"] == 4000 and r["emergency_amount"] == 4000  # חוסר 30,000 בקרן החירום


def test_get_monthly_allocation_counts_emergency_already_deposited():
    s, uid = setup()
    s.add_salary_event(uid, {"period": "2026-10", "net": 20000, "allocation": {"emergency_amount": 29000}})
    r = run_tool("get_monthly_allocation", {"amount": 4000}, s, uid, approved(), TODAY)
    assert r["emergency_amount"] == 1000  # נשארו 1,000 מתוך חוסר של 30,000


def test_tool_errors_are_returned_not_raised():
    s, uid = setup()
    assert "הפקדה חודשית" in run_tool("get_monthly_allocation", {}, s, uid, approved(monthly_deposit=None))["error"]
    assert "חיובי" in run_tool("get_monthly_allocation", {"amount": -5}, s, uid, approved())["error"]
    assert "error" in run_tool("nope", {}, s, uid, approved())
