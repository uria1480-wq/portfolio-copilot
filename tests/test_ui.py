from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.ui import banner_html, hero_html, profile_html, supported


def test_profile_states():
    assert "בבנייה" in profile_html(InvestorProfile())
    waiting = InvestorProfile(recommended_risk_level="מאוזן")
    assert "ממתין לאישור" in profile_html(waiting) and "pc-unconfirmed" in profile_html(waiting)
    ready = InvestorProfile(age=30, recommended_risk_level="אגרסיבי", risk_confirmed=True,
                            investment_horizon_years=20)
    out = profile_html(ready)
    assert "מוכן לחישוב" in out and "pc-risk-high" in out and "pc-unconfirmed" not in out


def test_user_text_is_escaped_everywhere():
    evil = '<script>alert(1)</script>'
    p = InvestorProfile(restrictions=[evil], agent_reasoning=evil, relevant_vehicles=[evil])
    assert evil not in profile_html(p) and "&lt;script&gt;" in profile_html(p)
    assert evil not in banner_html("❌ " + evil)


def test_banner_kinds():
    assert "pc-banner-ok" in banner_html("✅ נטען") and "pc-banner-err" in banner_html("❌ שגיאה")
    assert banner_html("") == ""


def test_supported_filters_unknown_params():
    def f(a, b=1): ...
    assert supported(f, a=1, c=2) == {"a": 1}


def test_hero_describes_current_flow_without_documents():
    out = hero_html()
    assert "ראיון, תמונת מצב, הצעה וניהול חודשי" in out and "מסמכים" not in out


def test_money_is_formatted_in_one_place():
    import inspect

    from portfolio_copilot import monthly, proposal, restrictions, situation, ui
    from portfolio_copilot.schemas import format_money

    assert format_money(12345.6) == "₪12,346" and situation.format_value("money", 1000) == "₪1,000"
    for module in (proposal, restrictions, monthly, situation, ui):
        assert 'f"₪{' not in inspect.getsource(module) and not hasattr(module, "_money")

