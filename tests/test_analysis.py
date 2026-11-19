import json
from datetime import date
from types import SimpleNamespace

from portfolio_copilot.analysis import Guidance, analyze, clamp_plan, default_guidance
from portfolio_copilot.intake import IntakeAnswers
from portfolio_copilot.plan import SavingsPlan

A = IntakeAnswers(age=35, status="שכיר/ה", monthly_net_income=40000, monthly_expenses=15000, can_save_monthly=10000,
                  liquid_savings=60000)
PIC = {"monthly_net_income": 40000, "can_save_monthly": 10000, "emergency_months": 4.0, "savings_rate": 0.25,
       "items": [], "total": 60000, "gaps": ["לא הועלה דוח לקרן פנסיה ולא הוזן שווי"]}


def fake_client(content):
    msg = SimpleNamespace(content=content)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=msg)]))))


GOOD = {"summary": "מצב טוב", "risk_level": "מאוזן", "risk_reasoning": "אופק בינוני",
        "steps": [{"title": "להעלות דוח פנסיה", "why": "חסר מידע"}, {"title": "להפריש כל חודש", "why": "הרגל"}],
        "plan": {"savings_mode": "fixed", "savings_value": 9000,
                 "buckets": [{"name": "קרן חירום", "kind": "cash", "share": 0.2}, {"name": "השקעות", "kind": "invest", "share": 0.8}],
                 "rationale": "מתאים"}}


def test_fallback_cash_share_follows_emergency_months():
    for months, expected_cash in ((1.0, 0.6), (4.0, 0.2), (8.0, 0.0), (None, 0.3)):
        g = default_guidance(A, {**PIC, "emergency_months": months}, "מאוזן")
        cash = sum(b.share for b in g.plan.buckets if b.kind == "cash")
        assert round(cash, 2) == expected_cash and g.plan.savings_value == 10000 and g.source == "fallback"


def test_fallback_guidance_mentions_missing_pension_info():
    g = default_guidance(A, PIC, "מאוזן")
    assert any("פנסיוני" in s.title for s in g.steps) and g.plan.rationale


def test_valid_model_answer_is_used_and_plan_stays_unconfirmed():
    g = analyze(A, PIC, "מאוזן", ["אופק"], fake_client(json.dumps(GOOD, ensure_ascii=False)), "m")
    assert g.source == "llm" and g.summary == "מצב טוב" and len(g.steps) == 2
    assert g.plan.savings_value == 9000 and not g.plan.confirmed


def test_model_cannot_plan_more_than_the_user_can_save():
    greedy = {**GOOD, "plan": {**GOOD["plan"], "savings_value": 25000}}
    assert analyze(A, PIC, "מאוזן", [], fake_client(json.dumps(greedy, ensure_ascii=False)), "m").plan.savings_value == 10000
    pct = SavingsPlan(savings_mode="percent", savings_value=0.6)
    assert clamp_plan(pct, A).savings_value == 0.25


def test_broken_model_answer_falls_back_to_rule_based_guidance(capsys):
    for bad in ("סתם טקסט", "{}", '{"summary": "", "steps": []}'):
        g = analyze(A, PIC, "מאוזן", [], fake_client(bad), "m")
        assert g.source == "fallback" and g.plan.savings_value == 10000
    assert "נכשל" in capsys.readouterr().out


def test_missing_risk_level_in_model_answer_uses_the_questionnaire_result():
    g = analyze(A, PIC, "שמרני", [], fake_client(json.dumps({**GOOD, "risk_level": "לא ברור"}, ensure_ascii=False)), "m")
    assert g.risk_level == "שמרני"


def test_analysis_prompt_includes_injected_date():
    seen = []
    msg = SimpleNamespace(content=json.dumps(GOOD, ensure_ascii=False))

    def create(**kw):
        seen.append(kw["messages"])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    analyze(A, PIC, "מאוזן", [], client, "m", today=date(2026, 11, 19))
    assert "התאריך היום: 2026-11-19" in seen[0][0]["content"]


def test_guidance_roundtrips_through_json_for_storage():
    g = default_guidance(A, PIC, "מאוזן")
    assert Guidance.model_validate(g.model_dump(mode="json")) == g