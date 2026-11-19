from portfolio_copilot.db import Store
from portfolio_copilot.intake import IntakeAnswers, derive_profile, missing_fields, parse_restrictions, risk_assessment


def answers(**kw):
    base = dict(age=35, status="שכיר/ה", monthly_net_income=40000, monthly_expenses=15000, can_save_monthly=10000,
                liquid_savings=60000, goals=["פרישה"], horizon_label="7 עד 15 שנים",
                reaction_label="לא אעשה כלום ואחכה", experience_label="קצת ניסיון", max_weight_label="עד 20%")
    return IntakeAnswers(**{**base, **kw})


def test_missing_fields_lists_required_questions_in_hebrew():
    assert missing_fields(IntakeAnswers()) == ["גיל", "מצב תעסוקתי", "הכנסה נטו חודשית", "כמה אפשר להפריש בחודש",
                                               "אופק השקעה", "תגובה לירידה בתיק", "ניסיון בהשקעות"]
    assert missing_fields(answers()) == []


def test_risk_depends_on_the_person():
    assert risk_assessment(answers())[0] == "מאוזן"
    bold = answers(age=25, horizon_label="יותר מ-15 שנים", reaction_label="אקנה עוד, זו הזדמנות", experience_label="מנוסה")
    assert risk_assessment(bold)[0] == "אגרסיבי"
    senior = answers(age=68, status="פנסיונר/ית", horizon_label="עד 3 שנים", reaction_label="אמכור חלק", experience_label="אין לי ניסיון")
    level, reasons, _ = risk_assessment(senior)
    assert level == "שמרני" and any("גיל" in r for r in reasons)


def test_low_emergency_fund_lowers_risk_score():
    rich = risk_assessment(answers(liquid_savings=100000))[2]
    thin = risk_assessment(answers(liquid_savings=10000))[2]
    assert thin == rich - 1


def test_derive_profile_maps_the_answers_and_leaves_risk_unconfirmed():
    p = derive_profile(answers(restrictions_text="לא מוכר צים\nלא קונה נפט, עישון"))
    assert p.age == 35 and p.monthly_deposit == 10000 and p.investment_horizon_years == 10
    assert p.max_single_asset_weight == 0.20 and p.recommended_risk_level == "מאוזן" and not p.risk_confirmed
    assert p.restrictions == ["לא מוכר צים", "לא קונה נפט", "עישון"] and p.investment_goal == "פרישה"
    assert derive_profile(answers(age=16, status="תלמיד/ה")).life_stage == "נוער"
    assert derive_profile(answers(age=70, status="פנסיונר/ית")).needs_cashflow is True
    assert derive_profile(answers(age=58)).life_stage == "לקראת פרישה"


def test_parse_restrictions():
    assert parse_restrictions("") == [] and parse_restrictions(" a ,, b;\nc ") == ["a", "b", "c"]


def test_state_storage_roundtrip():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    assert s.load_state(uid, "intake") is None
    s.save_state(uid, "intake", answers().model_dump())
    assert IntakeAnswers.model_validate(s.load_state(uid, "intake")) == answers()