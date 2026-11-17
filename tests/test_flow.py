"""בדיקת המסע המלא דרך הפונקציות של הממשק: שיחת היכרות, תמונת מצב, ניתוח, אישור ומשכורת."""
import json
import os

import pytest

pytest.importorskip("gradio")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from types import SimpleNamespace

from test_agent_flow import Call, FakeClient, Msg

from portfolio_copilot import agent
from portfolio_copilot import app as appmod
from portfolio_copilot.db import Store
from portfolio_copilot.intake import HORIZON_OPTIONS, IntakeAnswers
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.ui import intake_progress_html

FETCH = lambda symbol: 100.0
GUIDANCE = {"summary": "מצב יציב", "risk_level": "מאוזן", "risk_reasoning": "אופק בינוני",
            "steps": [{"title": "להפריש כל חודש", "why": "הרגל"}],
            "plan": {"savings_mode": "fixed", "savings_value": 10000, "rationale": "מתאים",
                     "buckets": [{"name": "קרן חירום", "kind": "cash", "share": 0.3}, {"name": "השקעות", "kind": "invest", "share": 0.7}]}}


def llm(content):
    msg = SimpleNamespace(content=content)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=msg)]))))


def new_store():
    store = Store(":memory:")
    return store, store.get_or_create_user("demo")


def complete_profile(**extra):
    return InvestorProfile(age=35, investment_horizon_years=10, recommended_risk_level="מאוזן",
                           risk_confirmed=True, monthly_deposit=10000, **extra)


def say(monkeypatch, handler, text, history, profile, *tool_calls, reply="הבנתי"):
    """תור אחד בשלב 1: המודל המדומה מפעיל את הכלים שהועברו ואז עונה בטקסט."""
    calls = [Call(f"c{i}", name, json.dumps(args, ensure_ascii=False)) for i, (name, args) in enumerate(tool_calls)]
    fake = FakeClient([Msg(tool_calls=calls), Msg(content=reply)] if calls else [Msg(content=reply)])
    monkeypatch.setattr(agent, "client", fake)
    return handler(text, history, profile), fake


def test_full_journey(monkeypatch):
    store, uid = new_store()
    assert not any(appmod.stage_flags(store, uid).values())
    chat = appmod.make_intake_chat_handler(store, uid, fetch=FETCH)

    # 1. שיחת היכרות: הפרופיל נבנה דרך הכלים, תור אחרי תור
    history = appmod.intake_opening(store.load_profile(uid))
    out, fake = say(monkeypatch, chat, "אני בן 35", history, None,
                    ("update_profile", {"age": 35}), reply="מה אופק ההשקעה?")
    msg, history, profile, panel, side_panel, stages = out
    assert msg == "" and [m["role"] for m in history] == ["assistant", "user", "assistant"]
    assert history[-1]["content"] == "מה אופק ההשקעה?"
    assert fake.calls[0]["messages"][2]["content"] == appmod.INTAKE_GREETING  # הפתיח נשלח למודל כהקשר
    assert profile.age == 35 and store.load_profile(uid).age == 35
    assert "חסרים 4" in panel and not appmod.stage_flags(store, uid)["intake"]

    out, _ = say(monkeypatch, chat, "10 שנים. ואני לא מוכר את ZIM", history, profile,
                 ("update_profile", {"investment_horizon_years": 10, "recommended_risk_level": "מאוזן",
                                     "agent_reasoning": "אופק בינוני"}),
                 ("add_restriction", {"symbol": "ZIM"}), reply="מציע רמת סיכון מאוזנת. מתאים לך?")
    _, history, profile, panel, _, _ = out
    assert profile.no_sell_symbols == ["ZIM"] and "ממתין לאישור" in panel

    out, _ = say(monkeypatch, chat, "מאשר. אפשר 10,000 בחודש", history, profile,
                 ("update_profile", {"risk_confirmed": True, "monthly_deposit": 10000}), reply="הפרופיל מלא")
    _, history, profile, panel, side_panel, stages = out
    assert profile.is_complete() and "הפרופיל מלא ונשמר" in panel and "מוכן לחישוב" in side_panel
    assert appmod.stage_flags(store, uid)["intake"] and "pc-step-done" in stages
    assert store.load_profile(uid) == profile

    # 2. המצב שלי: ערכים ידניים, החזקות ומסמך נכנסים לתמונה אחת
    appmod.make_assets_handler(store, uid, FETCH)(None, None, 150000, 40000, None)
    store.upsert_holding(uid, "VT", 100)
    store.save_document(uid, {"doc_type": "fund_report", "period": "2026-Q1", "data": {}, "warnings": [],
                              "summary": {"fund_type": "pension", "fund_name": "קרן", "provider": "חברה", "balance_end": 200000.0}})
    pic = appmod.compute_picture(store, uid, FETCH)
    values = {i["label"]: i["value"] for i in pic["items"]}
    assert values["קרן פנסיה"] == 200000 and values["קרן השתלמות"] == 40000 and values["תיק השקעות"] == 10000.0
    assert pic["can_save_monthly"] == 10000  # ההפקדה החודשית מהשיחה
    assert appmod.stage_flags(store, uid)["picture"]

    # 3. ניתוח ואישור
    analysis = appmod.make_analysis_handler(store, uid, llm(json.dumps(GUIDANCE, ensure_ascii=False)), "m", FETCH)()
    assert "מצב יציב" in analysis[0] and analysis[1] == "מאוזן" and analysis[3] == 10000
    assert appmod.stage_flags(store, uid)["analysis"] and not appmod.stage_flags(store, uid)["monthly"]
    confirm = appmod.make_confirm_handler(store, uid)("מאוזן", "סכום קבוע בשקלים", 10000, 30, 40000)
    assert "התוכנית אושרה" in confirm[0] and "הפרופיל מלא ונשמר" in confirm[6]
    saved = store.load_profile(uid)
    assert store.load_plan(uid).is_ready() and saved.is_complete()
    assert saved.no_sell_symbols == ["ZIM"] and saved.age == 35  # האישור לא דורס את מה שנאסף בשיחה
    assert appmod.stage_flags(store, uid) == {"intake": True, "picture": True, "analysis": True, "monthly": True}

    # 4. ניהול חודשי: נכנסה משכורת
    html = appmod.make_salary_handler(store, uid, FETCH)(40000, 4000, 2500)
    assert "מה לעשות עם ₪10,000" in html and "העבר" in html and "קנה" in html and "₪16,500" in html
    assert len(store.list_salary_events(uid)) == 1


def test_rejected_value_is_not_saved(monkeypatch):
    store, uid = new_store()
    chat = appmod.make_intake_chat_handler(store, uid)
    out, fake = say(monkeypatch, chat, "אני בן 300", appmod.intake_opening(InvestorProfile()), None,
                    ("update_profile", {"age": 300}), reply="הגיל לא נראה תקין, מה הגיל שלך?")
    assert out[2].age is None and store.load_profile(uid).age is None
    tool_result = json.loads([m for m in fake.calls[1]["messages"] if m["role"] == "tool"][0]["content"])
    assert "age" in tool_result["rejected"] and tool_result["next_field"] == "age"


def test_empty_message_does_not_call_the_model(monkeypatch):
    store, uid = new_store()
    fake = FakeClient([Msg(content="לא אמור להגיע")])
    monkeypatch.setattr(agent, "client", fake)
    history = appmod.intake_opening(InvestorProfile())
    out = appmod.make_intake_chat_handler(store, uid)("   ", history, None)
    assert out[1] == history and fake.calls == []


def test_model_error_keeps_profile_and_shows_message(monkeypatch):
    store, uid = new_store()
    store.save_profile(uid, InvestorProfile(age=40))

    def boom(**kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(agent, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom))))
    out = appmod.make_intake_chat_handler(store, uid)("היי", [], None)
    assert "שגיאה" in out[1][-1]["content"] and out[2].age == 40 and store.load_profile(uid).age == 40


def test_opening_message_depends_on_profile():
    assert appmod.intake_opening(InvestorProfile())[0]["content"] == appmod.INTAKE_GREETING
    assert appmod.intake_opening(complete_profile())[0]["content"] == appmod.INTAKE_DONE_GREETING


def test_analysis_before_interview_is_blocked_and_confirm_needs_a_risk_level():
    store, uid = new_store()
    out = appmod.make_analysis_handler(store, uid, llm("{}"), "m", FETCH)()
    assert "השלם קודם את שיחת ההיכרות" in out[0] and "גיל" in out[0]
    assert "השלם קודם" in appmod.make_confirm_handler(store, uid)("מאוזן", "סכום קבוע בשקלים", 1000, 30, None)[0]
    store.save_profile(uid, complete_profile())
    assert "בחר רמת סיכון" in appmod.make_confirm_handler(store, uid)(None, "סכום קבוע בשקלים", 1000, 30, None)[0]
    assert "הזן סכום" in appmod.make_confirm_handler(store, uid)("מאוזן", "סכום קבוע בשקלים", None, 30, None)[0]


def test_model_failure_still_leads_to_a_usable_plan():
    store, uid = new_store()
    store.save_profile(uid, complete_profile())
    out = appmod.make_analysis_handler(store, uid, llm("לא JSON"), "m", FETCH)()
    assert "ניתוח בסיסי" in out[0] and out[3] == 10000


def old_form_answers():
    return IntakeAnswers(age=99, status="שכיר/ה", monthly_net_income=20000, monthly_expenses=8000,
                         can_save_monthly=3000, liquid_savings=50000, horizon_label="עד 3 שנים",
                         restrictions_text="ישן", pension_value=5000, study_fund_value=7000, other_assets=9000).model_dump()


def test_answers_come_only_from_profile_and_stage2_values():
    store, uid = new_store()
    store.save_state(uid, "intake", old_form_answers())
    store.save_profile(uid, complete_profile(investment_goal="דירה", restrictions=["לא למכור: ZIM"]))
    appmod.make_assets_handler(store, uid, FETCH)(18000, 30000, None, None, None)
    a = appmod.load_answers(store, uid)
    assert (a.age, a.can_save_monthly, a.horizon_label, a.goals) == (35, 10000, "7 עד 15 שנים", ["דירה"])
    assert a.restrictions_text == "לא למכור: ZIM"
    assert (a.monthly_net_income, a.liquid_savings) == (18000, 30000)
    assert a.monthly_expenses is None and a.status is None and a.pension_value is None  # לא מהטופס הישן


def test_old_intake_in_db_does_not_reach_the_picture():
    store, uid = new_store()
    store.save_state(uid, "intake", old_form_answers())
    pic = appmod.compute_picture(store, uid, FETCH)
    values = {i["label"]: (i["value"], i["source"]) for i in pic["items"]}
    for label in ("כסף נזיל וחסכונות בבנק", "קרן פנסיה", "קרן השתלמות", "נכסים אחרים"):
        assert values[label] == (None, None)
    assert pic["total"] is None and pic["monthly_net_income"] is None and pic["can_save_monthly"] is None
    assert pic["emergency_months"] is None and pic["savings_rate"] is None
    gaps = " ".join(pic["gaps"])
    assert "חסרה הכנסה נטו" in gaps and "כסף נזיל" in gaps and "פנסיה" in gaps and "השתלמות" in gaps
    assert not appmod.stage_flags(store, uid)["picture"]  # הטופס הישן לא נחשב כמידע לשלב 2
    html = appmod.picture_html(pic)
    for old in ("20,000", "50,000", "5,000", "7,000", "9,000"):
        assert old not in html
    assert "הכנסה נטו חודשית" in html and "—" in html


def test_stage2_manual_values_fill_the_picture():
    store, uid = new_store()
    out = appmod.make_assets_handler(store, uid, FETCH)(18000, 30000, 100000, None, 0)
    assert "הערכים נשמרו" in out[0] and store.load_state(uid, "assets")["liquid_savings"] == 30000
    pic = appmod.compute_picture(store, uid, FETCH)
    values = {i["label"]: (i["value"], i["source"]) for i in pic["items"]}
    assert values["כסף נזיל וחסכונות בבנק"] == (30000, "הזנה ידנית") and values["קרן פנסיה"] == (100000, "הזנה ידנית")
    assert pic["monthly_net_income"] == 18000 and not any("כסף נזיל" in g or "הכנסה" in g for g in pic["gaps"])
    assert "₪18,000" in appmod.picture_html(pic)
    bad = appmod.make_assets_handler(store, uid, FETCH)(-1, None, None, None, None)
    assert "חיוביים" in bad[0] and store.load_state(uid, "assets")["monthly_net_income"] == 18000


def test_horizon_labels_match_known_options():
    for years, expected in ((1, "עד 3 שנים"), (3, "עד 3 שנים"), (5, "3 עד 7 שנים"), (15, "7 עד 15 שנים"), (30, "יותר מ-15 שנים")):
        assert appmod.horizon_label(years) == expected and expected in HORIZON_OPTIONS
    assert appmod.horizon_label(None) is None


def test_intake_progress_card():
    partial = intake_progress_html(InvestorProfile(age=30, recommended_risk_level="מאוזן"))
    assert "חסרים 3" in partial and "✓ גיל או שלב בחיים" in partial and "◯ אישור רמת הסיכון" in partial
    assert "הפרופיל מלא" not in partial
    assert "הפרופיל מלא ונשמר" in intake_progress_html(complete_profile())
    empty = intake_progress_html(InvestorProfile())
    assert "חסרים 5" in empty and "◯ אישור רמת הסיכון" in empty


def test_demo_builds_with_chat_intake():
    store, uid = new_store()
    demo, _ = appmod.build_demo(store, uid)
    labels = {getattr(b, "label", None) for b in demo.blocks.values()}
    assert "שיחת היכרות" in labels and "גיל" not in labels  # טופס השאלון כבר לא בשלב 1
