"""שלב 2 "המצב שלי": הנתונים מוצגים מהפרופיל בלבד (מקור "ראיון"). חסר מוצג כ-"—"."""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from portfolio_copilot.db import Store
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


def test_partial_profile_shows_empty_fields_as_dash():
    view = build_situation(InvestorProfile(age=30, monthly_net_income=9000))
    r = rows(view)
    assert r["age"]["display"] == "30" and r["age"]["source"] == "ראיון"
    assert r["monthly_net_income"]["display"] == "₪9,000" and r["monthly_net_income"]["source"] == "ראיון"
    for key in ("marital_status", "employment_status", "monthly_expenses", "liquid_savings", "pension_balance",
                "study_fund_balance", "other_assets", "investment_goal", "investment_horizon_years"):
        assert r[key]["display"] == "—" and r[key]["source"] is None and r[key]["status"] == "missing"
    assert "spouse_monthly_net_income" not in r  # לא נדרש
    assert "holdings" not in r and "gemel" not in r  # אין יותר שורות תיק וגמל
    assert view["total"] is None
    gaps = " ".join(view["gaps"])
    assert "כסף נזיל" in gaps and "קרן פנסיה" in gaps and "החזקות" not in gaps
    assert "הכנסה נטו" not in gaps  # נאספה בראיון


def test_full_profile_shows_all_values_with_interview_source():
    view = build_situation(FULL)
    r = rows(view)
    for key in PROFILE_KEYS:
        assert r[key]["source"] == "ראיון" and r[key]["status"] == "known", key
        assert r[key]["display"] == format_value("money" if isinstance(r[key]["value"], float) else
                                                 "years" if key == "investment_horizon_years" else "text",
                                                 r[key]["value"])
    assert r["spouse_monthly_net_income"]["display"] == "₪11,000"
    assert r["investment_horizon_years"]["display"] == "12 שנים" and r["marital_status"]["display"] == "נשוי"
    assert view["total"] == 45000 + 210000 + 60000 + 15000
    assert view["gaps"] == []  # כל שדות הראיון ידועים


def test_unknown_is_dash_not_zero_and_none_is_zero():
    p = InvestorProfile(unknown_fields=["pension_balance"], monthly_debt_payments=0.0, other_assets=0.0)
    r = rows(build_situation(p))
    assert r["pension_balance"]["display"] == "—" and r["pension_balance"]["value"] is None
    assert r["pension_balance"]["source"] == "ראיון" and r["pension_balance"]["status"] == "unknown"
    assert r["monthly_debt_payments"]["display"] == "₪0" and r["other_assets"]["display"] == "₪0"


def test_spouse_income_row_only_when_partnered():
    assert "spouse_monthly_net_income" not in rows(build_situation(InvestorProfile(marital_status="רווק")))
    r = rows(build_situation(InvestorProfile(marital_status="ידוע בציבור")))
    assert r["spouse_monthly_net_income"]["display"] == "—"


def test_old_intake_and_old_manual_values_are_not_displayed():
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    # נתונים ישנים שאולי עוד נמצאים במסד קיים (טבלת state כבר לא בשימוש)
    for key, data in (("intake", '{"monthly_net_income": 20000, "liquid_savings": 50000}'),
                      ("assets", '{"monthly_net_income": 18000, "pension_value": 7000}')):
        store.conn.execute("INSERT INTO state VALUES (?, ?, ?, '2026-01-01')", (uid, key, data))
    store.save_profile(uid, InvestorProfile(age=30))
    r = rows(load_situation(store, uid))
    assert r["age"]["display"] == "30"
    for key in ("monthly_net_income", "liquid_savings", "pension_balance"):
        assert r[key]["display"] == "—" and r[key]["source"] is None


def test_stored_holdings_and_documents_are_ignored():
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    store.conn.execute("INSERT INTO holdings (user_id, symbol, quantity, updated_at) VALUES (?, 'VT', 10, '2026-01-01')", (uid,))
    store.save_document(uid, {"doc_type": "fund_report", "period": "2026-Q1", "data": {}, "warnings": [],
                              "summary": {"fund_type": "pension", "fund_name": "קרן", "provider": "חברה",
                                          "balance_end": 250000.0}})
    store.save_document(uid, {"doc_type": "payslip", "period": "2026-10", "data": {}, "warnings": [],
                              "summary": {"period": "2026-10", "net_to_bank": 17200.0}})
    store.save_profile(uid, InvestorProfile(age=30, pension_balance=90000))
    r = rows(load_situation(store, uid))
    assert (r["pension_balance"]["value"], r["pension_balance"]["source"]) == (90000, "ראיון")
    assert r["monthly_net_income"]["display"] == "—" and "holdings" not in r and "gemel" not in r


def test_situation_html_renders_dash_sources_and_escapes():
    evil = "<script>x</script>"
    html = situation_html(build_situation(InvestorProfile(investment_goal=evil, unknown_fields=["liquid_savings"])),
                          prefix="✅ נשמר")
    assert evil not in html and "&lt;script&gt;" in html
    assert "—" in html and "ראיון" in html and "pc-banner-ok" in html
    assert "מה עוד חסר" in html and "עדיין אין נכסים ידועים" in html



# ---------- דיווחים חודשיים בדשבורד ----------
BASE = InvestorProfile(age=40, liquid_savings=50000, pension_balance=100000, study_fund_balance=40000, other_assets=0)


def report(set_aside, pension, study, **extra):
    return {"period": "2026-11", "net": 20000, "set_aside": set_aside, "pension_contributions": pension,
            "study_fund_contributions": study, "total_pension": pension, "total_study_fund": study, **extra}


def test_without_history_dashboard_is_unchanged():
    assert build_situation(BASE, []) == build_situation(BASE) == build_situation(BASE, None)
    assert situation_html(build_situation(BASE, [])) == situation_html(build_situation(BASE))
    assert all(r["added"] is None and r["detail"] is None for r in rows(build_situation(BASE)).values())


def test_three_reports_add_up_with_separate_source():
    history = [report(3000, 2000, 800), report(4000, 2000, 800), report(5000, 2100, 900)]
    view = build_situation(BASE, history)
    r = rows(view)
    assert (r["liquid_savings"]["value"], r["liquid_savings"]["added"]) == (62000, 12000)
    assert (r["pension_balance"]["value"], r["pension_balance"]["added"]) == (106100, 6100)
    assert (r["study_fund_balance"]["value"], r["study_fund_balance"]["added"]) == (42500, 2500)
    assert r["other_assets"]["added"] is None and r["age"]["added"] is None
    liquid = r["liquid_savings"]
    assert liquid["source"] == "ראיון" and liquid["added_source"] == "דיווח חודשי"
    assert liquid["detail"] == "₪50,000 מהראיון + ₪12,000 מדיווחים חודשיים"
    assert view["total"] == 62000 + 106100 + 42500 + 0
    html = situation_html(view)
    assert "דיווח חודשי" in html and "₪50,000 מהראיון + ₪12,000 מדיווחים חודשיים" in html


def test_partner_contributions_are_included():
    married = report(5000, 2000, 800, partner_pension=1500, partner_study_fund=600, total_pension=3500,
                     total_study_fund=1400)
    r = rows(build_situation(BASE, [married]))
    assert r["pension_balance"]["value"] == 103500 and r["study_fund_balance"]["value"] == 41400


def test_old_reports_without_combined_fields_use_own_values():
    old = {"period": "2026-01", "net": 9000, "set_aside": 1000, "pension_contributions": 700}
    r = rows(build_situation(BASE, [old]))
    assert (r["liquid_savings"]["value"], r["pension_balance"]["value"], r["study_fund_balance"]["value"]) == (
        51000, 100700, 40000)


def test_missing_base_is_not_invented():
    r = rows(build_situation(InvestorProfile(age=40), [report(3000, 0, 0)]))
    assert r["liquid_savings"]["value"] is None and r["liquid_savings"]["added"] == 3000
    assert "הבסיס מהראיון חסר" in r["liquid_savings"]["detail"]


def test_profile_is_not_changed_by_history():
    profile = BASE.model_copy()
    build_situation(profile, [report(3000, 2000, 800)])
    assert profile == BASE
