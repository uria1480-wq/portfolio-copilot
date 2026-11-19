"""שלב 2 "המצב שלי": הנתונים מוצגים מהפרופיל (מקור "ראיון") וממסמכים (מקור "מסמך"). חסר מוצג כ-"—"."""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from portfolio_copilot.db import Store
from portfolio_copilot.intake import IntakeAnswers
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.situation import build_situation, format_value, load_situation
from portfolio_copilot.ui import situation_html

PROFILE_KEYS = ["age", "marital_status", "employment_status", "monthly_net_income", "spouse_monthly_net_income",
                "monthly_expenses", "monthly_debt_payments", "monthly_deposit", "liquid_savings", "pension_balance",
                "study_fund_balance", "other_assets", "investment_goal", "investment_horizon_years"]

FULL = InvestorProfile(age=38, marital_status="נשוי", spouse_monthly_net_income=11000, employment_status="שכיר/ה",
                       monthly_net_income=16000, monthly_expenses=12000, monthly_debt_payments=2500,
                       monthly_deposit=3000, liquid_savings=45000, pension_balance=210000, study_fund_balance=60000,
                       other_assets=15000, investment_goal="דירה", investment_horizon_years=12)


def rows(view):
    return {r["key"]: r for s in view["sections"] for r in s["rows"]}


def report(fund_type, balance, name="קופה"):
    return {"summary": {"fund_type": fund_type, "balance_end": balance, "fund_name": name, "provider": "חברה"}}


def test_partial_profile_shows_empty_fields_as_dash():
    view = build_situation(InvestorProfile(age=30, monthly_net_income=9000), [], [])
    r = rows(view)
    assert r["age"]["display"] == "30" and r["age"]["source"] == "ראיון"
    assert r["monthly_net_income"]["display"] == "₪9,000" and r["monthly_net_income"]["source"] == "ראיון"
    for key in ("marital_status", "employment_status", "monthly_expenses", "liquid_savings", "pension_balance",
                "study_fund_balance", "other_assets", "investment_goal", "investment_horizon_years", "holdings"):
        assert r[key]["display"] == "—" and r[key]["source"] is None and r[key]["status"] == "missing"
    assert "spouse_monthly_net_income" not in r and "gemel" not in r  # לא נדרש / אין מסמך
    assert view["total"] is None
    gaps = " ".join(view["gaps"])
    assert "כסף נזיל" in gaps and "קרן פנסיה" in gaps and "לא נטען קובץ החזקות" in gaps
    assert "הכנסה נטו" not in gaps  # נאספה בראיון


def test_full_profile_shows_all_values_with_interview_source():
    view = build_situation(FULL, [], [])
    r = rows(view)
    for key in PROFILE_KEYS:
        assert r[key]["source"] == "ראיון" and r[key]["status"] == "known", key
        assert r[key]["display"] == format_value("money" if isinstance(r[key]["value"], float) else
                                                 "years" if key == "investment_horizon_years" else "text",
                                                 r[key]["value"])
    assert r["spouse_monthly_net_income"]["display"] == "₪11,000"
    assert r["investment_horizon_years"]["display"] == "12 שנים" and r["marital_status"]["display"] == "נשוי"
    assert view["total"] == 45000 + 210000 + 60000 + 15000
    assert view["gaps"] == ["לא נטען קובץ החזקות"]  # כל שדות הראיון ידועים


def test_unknown_is_dash_not_zero_and_none_is_zero():
    p = InvestorProfile(unknown_fields=["pension_balance"], monthly_debt_payments=0.0, other_assets=0.0)
    r = rows(build_situation(p, [], []))
    assert r["pension_balance"]["display"] == "—" and r["pension_balance"]["value"] is None
    assert r["pension_balance"]["source"] == "ראיון" and r["pension_balance"]["status"] == "unknown"
    assert r["monthly_debt_payments"]["display"] == "₪0" and r["other_assets"]["display"] == "₪0"


def test_document_values_win_and_are_marked_document():
    view = build_situation(FULL, [report("pension", 250000), report("provident_investment", 30000)],
                           [{"summary": {"net_to_bank": 17200}}], holdings_value=12000.0, has_holdings=True)
    r = rows(view)
    assert (r["pension_balance"]["value"], r["pension_balance"]["source"]) == (250000, "מסמך")
    assert (r["monthly_net_income"]["display"], r["monthly_net_income"]["source"]) == ("₪17,200", "מסמך")
    assert (r["gemel"]["display"], r["gemel"]["source"]) == ("₪30,000", "מסמך")
    assert (r["holdings"]["display"], r["holdings"]["source"]) == ("₪12,000", "מסמך")
    assert r["study_fund_balance"]["source"] == "ראיון"  # אין דוח השתלמות, נשאר מהראיון
    assert view["total"] == 45000 + 12000 + 250000 + 60000 + 30000 + 15000


def test_only_the_latest_report_per_fund_counts():
    newest_first = [report("pension", 210000, "מגדל"), report("pension", 200000, "מגדל"),
                    report("pension", 50000, "הראל")]
    assert rows(build_situation(InvestorProfile(), newest_first, []))["pension_balance"]["value"] == 260000


def test_spouse_income_row_only_when_partnered():
    assert "spouse_monthly_net_income" not in rows(build_situation(InvestorProfile(marital_status="רווק"), [], []))
    r = rows(build_situation(InvestorProfile(marital_status="ידוע בציבור"), [], []))
    assert r["spouse_monthly_net_income"]["display"] == "—"


def test_old_intake_and_old_manual_values_are_not_displayed():
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    store.save_state(uid, "intake", IntakeAnswers(monthly_net_income=20000, liquid_savings=50000,
                                                  pension_value=5000).model_dump())
    store.save_state(uid, "assets", {"monthly_net_income": 18000, "liquid_savings": 30000, "pension_value": 7000})
    store.save_profile(uid, InvestorProfile(age=30))
    r = rows(load_situation(store, uid))
    assert r["age"]["display"] == "30"
    for key in ("monthly_net_income", "liquid_savings", "pension_balance"):
        assert r[key]["display"] == "—" and r[key]["source"] is None


def test_load_situation_prices_holdings_and_reports_price_errors():
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    store.upsert_holding(uid, "VT", 10)
    assert rows(load_situation(store, uid, fetch=lambda s: 100.0))["holdings"]["display"] == "₪1,000"

    def broken(symbol):
        raise ValueError("no price")

    view = load_situation(store, uid, fetch=broken)
    assert rows(view)["holdings"]["display"] == "—"
    assert "לא נמצאו מחירים לתיק ההשקעות" in view["gaps"] and "לא נמצא מחיר עבור VT" in view["gaps"]


def test_situation_html_renders_dash_sources_and_escapes():
    evil = "<script>x</script>"
    html = situation_html(build_situation(InvestorProfile(investment_goal=evil, unknown_fields=["liquid_savings"]), [], []),
                          prefix="✅ נשמר")
    assert evil not in html and "&lt;script&gt;" in html
    assert "—" in html and "ראיון" in html and "pc-banner-ok" in html
    assert "מה עוד חסר" in html and "עדיין אין נכסים ידועים" in html
