from portfolio_copilot.schemas import InvestorProfile, merge_profile
from portfolio_copilot.ui import (banner_html, documents_html, holdings_html, knowledge_html,
                                  profile_html, supported)


def test_profile_states():
    assert "בבנייה" in profile_html(InvestorProfile())
    waiting = merge_profile(InvestorProfile(), {"recommended_risk_level": "מאוזן"})
    assert "ממתין לאישור" in profile_html(waiting) and "pc-unconfirmed" in profile_html(waiting)
    ready = merge_profile(InvestorProfile(), {"age": 30, "recommended_risk_level": "אגרסיבי",
                                              "risk_confirmed": True, "investment_horizon_years": 20})
    out = profile_html(ready)
    assert "מוכן לחישוב" in out and "pc-risk-high" in out and "pc-unconfirmed" not in out


def test_user_text_is_escaped_everywhere():
    evil = '<script>alert(1)</script>'
    p = merge_profile(InvestorProfile(), {"restrictions": [evil], "agent_reasoning": evil, "relevant_vehicles": [evil]})
    assert evil not in profile_html(p) and "&lt;script&gt;" in profile_html(p)
    assert evil not in holdings_html([{"symbol": evil, "quantity": 1, "avg_cost": None}])
    assert evil not in banner_html("❌ " + evil)
    assert evil not in knowledge_html([evil], evil)
    doc = {"summary": {"period": evil, "net_to_bank": 1, "pension_monthly_total": 2}, "warnings": [evil]}
    assert evil not in documents_html([doc])


def test_empty_states_and_tables():
    assert "עדיין לא נטענו" in holdings_html([])
    table = holdings_html([{"symbol": "VT", "quantity": 20, "avg_cost": 98.5}])
    assert "VT" in table and "₪98" in table or "₪99" in table
    assert "עדיין לא הועלו" in documents_html([])
    assert "ריקה" in knowledge_html([])


def test_documents_show_warnings():
    doc = {"summary": {"period": "2026-10", "net_to_bank": 9500.0, "pension_monthly_total": 1800.0},
           "warnings": ["ברוטו פחות ניכויי חובה לא שווה לנטו"]}
    out = documents_html([doc])
    assert "2026-10" in out and "₪9,500" in out and "לבדוק מול התלוש" in out


def test_banner_kinds():
    assert "pc-banner-ok" in banner_html("✅ נטען") and "pc-banner-err" in banner_html("❌ שגיאה")
    assert banner_html("") == ""


def test_supported_filters_unknown_params():
    def f(a, b=1): ...
    assert supported(f, a=1, c=2) == {"a": 1}


def test_fund_report_card_and_escaping():
    evil = "<b>x</b>"
    doc = {"doc_type": "fund_report", "warnings": [evil], "summary": {
        "fund_name": evil, "period": "2026-Q1", "balance_end": 103900.0,
        "fee_on_savings_pct": 0.40, "avg_fee_on_savings_pct": 0.60, "expected_annual_cost_pct": 0.70,
        "track_name": "עוקב מדדים", "track_return_pct": 3.9, "no_beneficiaries": True}}
    out = documents_html([doc])
    assert "2026-Q1" in out and "₪103,900" in out and "0.40%" in out and "ממוצע הקופה 0.60%" in out
    assert "לא נקבעו מוטבים" in out and "דוחות מקופות" in out and evil not in out


def test_documents_show_both_types_in_sections():
    slip = {"doc_type": "payslip", "warnings": [], "summary": {"period": "2026-10", "net_to_bank": 9500.0, "pension_monthly_total": 1800.0}}
    report = {"doc_type": "fund_report", "warnings": [], "summary": {"fund_name": "קופה", "period": "2026-Q1", "balance_end": 1000.0}}
    out = documents_html([slip, report])
    assert "תלושי שכר" in out and "דוחות מקופות" in out