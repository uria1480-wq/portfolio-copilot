from portfolio_copilot.schemas import InvestorProfile, merge_profile
from portfolio_copilot.ui import banner_html, profile_html, supported


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
    assert evil not in banner_html("❌ " + evil)


def test_banner_kinds():
    assert "pc-banner-ok" in banner_html("✅ נטען") and "pc-banner-err" in banner_html("❌ שגיאה")
    assert banner_html("") == ""


def test_supported_filters_unknown_params():
    def f(a, b=1): ...
    assert supported(f, a=1, c=2) == {"a": 1}

