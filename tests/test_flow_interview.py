"""זרימת ההיכרות דרך ה-handlers של הממשק: ראיון מלא, ערכים שנדחים, הודעת פתיחה וכרטיס ההתקדמות.
מכאן מיובאים גם העזרים המשותפים (new_store, complete_profile, say) לשני קובצי הזרימה האחרים."""
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
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.ui import intake_progress_html


def new_store():
    store = Store(":memory:")
    return store, store.get_or_create_user("demo")


FINANCE = dict(marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=40000, monthly_expenses=15000, liquid_savings=60000,
               monthly_debt_payments=0, pension_balance=200000, study_fund_balance=40000, other_assets=0,
               investment_goal="פרישה")


def complete_profile(**extra):
    return InvestorProfile(**{"age": 35, "investment_horizon_years": 10, "recommended_risk_level": "מאוזן",
                              "risk_confirmed": True, "monthly_deposit": 10000, **FINANCE, **extra})


def say(monkeypatch, handler, text, history, profile, *tool_calls, reply="הבנתי"):
    """תור אחד בשלב 1: המודל המדומה מפעיל את הכלים שהועברו ואז עונה בטקסט."""
    calls = [Call(f"c{i}", name, json.dumps(args, ensure_ascii=False)) for i, (name, args) in enumerate(tool_calls)]
    fake = FakeClient([Msg(tool_calls=calls), Msg(content=reply)] if calls else [Msg(content=reply)])
    monkeypatch.setattr(agent, "client", fake)
    return handler(text, history, profile), fake


def test_full_journey(monkeypatch):
    store, uid = new_store()
    assert not any(appmod.stage_flags(store, uid).values())
    chat = appmod.make_intake_chat_handler(store, uid)

    # 1. שיחת היכרות: הפרופיל נבנה דרך הכלים, תור אחרי תור
    history = appmod.intake_opening(store.load_profile(uid))
    out, fake = say(monkeypatch, chat, "אני בן 35", history, None,
                    ("update_profile", {"age": 35}), reply="מה אופק ההשקעה?")
    msg, history, profile, panel, side_panel, stages = out
    assert msg == "" and [m["role"] for m in history] == ["assistant", "user", "assistant"]
    assert history[-1]["content"] == "מה אופק ההשקעה?"
    assert fake.calls[0]["messages"][2]["content"] == appmod.INTAKE_GREETING  # הפתיח נשלח למודל כהקשר
    assert profile.age == 35 and store.load_profile(uid).age == 35
    # 12 שדות ראיון (בלי הכנסת בן/בת זוג, שעוד לא נדרשת), רמת סיכון ואישור שלה
    assert "חסרים 14" in panel and "◯ מצב משפחתי" in panel and "הכנסת בן/בת זוג" not in panel
    assert not appmod.stage_flags(store, uid)["intake"]

    out, _ = say(monkeypatch, chat, "רווק, שכיר, 40 אלף נטו, הוצאות 15 אלף, 60 אלף בבנק. פנסיה לא יודע, אין חובות",
                 history, profile,
                 ("update_profile", {"marital_status": "רווק", "employment_status": "שכיר/ה", "monthly_net_income": 40000,
                                     "monthly_expenses": 15000, "liquid_savings": 60000,
                                     "unknown_fields": ["pension_balance"],
                                     "none_fields": ["monthly_debt_payments", "study_fund_balance", "other_assets"]}),
                 reply="מה היעד שלך?")
    _, history, profile, panel, _, _ = out
    assert "✓ יתרת פנסיה" in panel and "✓ החזרי חובות" in panel and "◯ יעד" in panel

    out, _ = say(monkeypatch, chat, "פרישה, 10 שנים. ואני לא מוכר את ZIM", history, profile,
                 ("update_profile", {"investment_goal": "פרישה", "investment_horizon_years": 10,
                                     "recommended_risk_level": "מאוזן", "agent_reasoning": "אופק בינוני"}),
                 ("add_restriction", {"item": "ZIM"}), reply="מציע רמת סיכון מאוזנת. מתאים לך?")
    _, history, profile, panel, _, _ = out
    assert profile.no_buy_symbols == ["ZIM"] and "ממתין לאישור" in panel
    assert profile.unknown_fields == ["pension_balance"] and profile.monthly_debt_payments == 0

    out, _ = say(monkeypatch, chat, "מאשר. אפשר 10,000 בחודש", history, profile,
                 ("update_profile", {"risk_confirmed": True, "monthly_deposit": 10000}), reply="הפרופיל מלא")
    _, history, profile, panel, side_panel, stages = out
    assert profile.is_complete() and "הפרופיל מלא ונשמר" in panel and "מוכן לחישוב" in side_panel
    assert appmod.stage_flags(store, uid)["intake"] and "pc-step-done" in stages
    assert store.load_profile(uid) == profile

    # 2. המצב שלי: מהפרופיל בלבד
    assert appmod.stage_flags(store, uid)["picture"]

    # 2א. קבל הצעה: נבנית בקוד מהפרופיל
    proposal = appmod.make_proposal_handler(store, uid)()
    assert "1. ביטחון" in proposal and "2. ההון הקיים" in proposal and "3. פנסיה והשתלמות" in proposal
    assert appmod.stage_flags(store, uid) == {"intake": True, "picture": True, "monthly": False}

    # 3. ניהול חודשי: הדיווח החודשי מחולק לפי הפרופיל
    html = appmod.make_monthly_handler(store, uid)(40000, 4000, 2500, "סכום קבוע בשקלים", 10000)
    assert "מה לעשות עם ₪10,000" in html and "קרן חירום" in html and "₪16,500" in html and "למה" in html
    assert len(store.list_salary_events(uid)) == 1
    assert appmod.stage_flags(store, uid) == {"intake": True, "picture": True, "monthly": True}


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


def test_intake_progress_card():
    partial = intake_progress_html(InvestorProfile(age=30, recommended_risk_level="מאוזן"))
    assert "חסרים 13" in partial and "✓ גיל או שלב בחיים" in partial and "◯ אישור רמת הסיכון" in partial
    assert "הפרופיל מלא" not in partial
    assert "הפרופיל מלא ונשמר" in intake_progress_html(complete_profile())
    empty = intake_progress_html(InvestorProfile())
    assert "חסרים 15" in empty and "◯ אישור רמת הסיכון" in empty
    # הכנסת בן/בת זוג מופיעה רק כשהיא נדרשת
    assert "הכנסת בן/בת זוג" not in empty
    assert "הכנסת בן/בת זוג" not in intake_progress_html(InvestorProfile(marital_status="גרוש"))
    married = intake_progress_html(InvestorProfile(marital_status="נשוי"))
    assert "◯ הכנסת בן/בת זוג" in married and "✓ מצב משפחתי" in married and "חסרים 15" in married
    for label in ("מצב משפחתי", "מצב תעסוקתי", "הכנסה נטו חודשית", "הוצאות חודשיות", "כסף נזיל", "החזרי חובות",
                  "יתרת פנסיה", "יתרת השתלמות", "נכסים אחרים", "יעד"):
        assert f"◯ {label}" in empty
    # "לא יודע" נספר כנענה בכרטיס
    assert "✓ יתרת פנסיה" in intake_progress_html(InvestorProfile(unknown_fields=["pension_balance"]))
