from portfolio_copilot.plan import Bucket, SavingsPlan
from portfolio_copilot.ui import plan_html, salary_history_html, salary_result_html


def test_plan_card_states():
    assert "לא נבנתה" in plan_html(SavingsPlan())
    draft = SavingsPlan(savings_value=1000)
    assert "ממתינה לאישור" in plan_html(draft)
    ready = SavingsPlan(savings_mode="percent", savings_value=0.25, confirmed=True,
                        buckets=[Bucket(name="קרן חירום", kind="cash", share=0.4), Bucket(name="השקעות", kind="invest", share=0.6)])
    out = plan_html(ready, prefix="✅ נשמר")
    assert "מאושרת" in out and "25% מהנטו" in out and "קרן חירום 40%" in out and "pc-banner-ok" in out


def test_salary_result_is_escaped_and_complete():
    evil = "<script>x</script>"
    result = {"period": "2026-11", "net": 40000.0, "set_aside": 10000.0, "free_to_spend": 30000.0,
              "pension_contributions": 4000.0, "study_fund_contributions": 2500.0, "total_saved_this_month": 16500.0,
              "actions": [{"type": "transfer", "bucket": evil, "amount": 3000.0},
                          {"type": "buy", "symbol": "VT", "amount": 7000.0}],
              "cap_breached": True, "breaching_symbols": [evil], "warnings": [evil]}
    out = salary_result_html(result)
    assert evil not in out and "₪7,000" in out and "₪16,500" in out and "ההחלטה אם למכור שלך" in out


def test_history_and_empty_state():
    assert "עדיין לא נרשמו" in salary_history_html([])
    out = salary_history_html([{"period": "2026-11", "net": 1000.0, "set_aside": 100.0}], prefix="❌ בעיה")
    assert "2026-11" in out and "₪1,000" in out and "pc-banner-err" in out