"""בדיקת המסע המלא דרך הפונקציות של הממשק: שיחת היכרות, תמונת מצב, הצעה ודיווח חודשי."""
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

FETCH = lambda symbol: 100.0
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
                 ("add_restriction", {"symbol": "ZIM"}), reply="מציע רמת סיכון מאוזנת. מתאים לך?")
    _, history, profile, panel, _, _ = out
    assert profile.no_sell_symbols == ["ZIM"] and "ממתין לאישור" in panel
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
    html = appmod.make_monthly_handler(store, uid)(40000, 4000, 2500, "סכום בשקלים", 10000)
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


def test_fresh_flag_uses_memory_store_and_default_uses_file(monkeypatch):
    """בודק את שני המצבים בלי לפתוח את הקובץ האמיתי ובלי להפעיל את השרת."""
    paths, launched = [], []

    def fake_store(path="data/portfolio.db"):
        paths.append(path)
        return Store(":memory:")  # לא נוגעים ב-data/portfolio.db אמיתי

    def no_kb(*args, **kwargs):
        raise RuntimeError("בלי מאגר ידע בבדיקה")

    fake_demo = SimpleNamespace(launch=lambda **kw: launched.append(kw))
    monkeypatch.setattr(appmod, "Store", fake_store)
    monkeypatch.setattr(appmod, "KnowledgeBase", no_kb)
    monkeypatch.setattr(appmod, "build_demo", lambda store, uid, kb, kb_error: (fake_demo, {}))

    appmod.main(["--fresh"])
    appmod.main([])
    assert paths == [":memory:", "data/portfolio.db"] and len(launched) == 2
    assert appmod.parse_args(["--fresh"]).fresh and not appmod.parse_args([]).fresh


def test_fresh_store_starts_clean_every_time():
    first = appmod.open_store(fresh=True)
    uid = first.get_or_create_user("demo")
    first.save_profile(uid, complete_profile())
    second = appmod.open_store(fresh=True)
    assert second.load_profile(second.get_or_create_user("demo")) == InvestorProfile()


def test_demo_builds_with_chat_intake():
    store, uid = new_store()
    demo, _ = appmod.build_demo(store, uid)
    labels = {getattr(b, "label", None) for b in demo.blocks.values()}
    assert "שיחת היכרות" in labels and "גיל" not in labels  # טופס השאלון כבר לא בשלב 1


# ---------- דיווח חודשי ----------
def test_monthly_report_uses_profile_and_records_history():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(liquid_savings=100000))  # קרן חירום מלאה (יעד 90,000)
    html = appmod.make_monthly_handler(store, uid)(40000, 4000, 2500, "אחוז מהנטו", 25)
    assert "מה לעשות עם ₪10,000" in html and "25% מנטו של ₪40,000" in html
    assert "מדד מניות ארה&quot;ב" in html and "₪2,750" in html and "קרן חירום (" not in html
    assert "מכירה" in html and "קנה" not in html  # "אין הצעות מכירה", בלי פעולות קנייה של נכס ספציפי
    event = store.list_salary_events(uid)[0]
    assert (event["net"], event["set_aside"], event["period"]) == (40000, 10000, event["allocation"]["as_of"][:7])


def test_monthly_report_errors_are_shown_and_nothing_is_saved():
    store, uid = new_store()
    store.save_profile(uid, complete_profile())
    handler = appmod.make_monthly_handler(store, uid)
    assert "הזן כמה נכנס נטו" in handler(None, None, None, "סכום בשקלים", 1000)
    assert "הזן כמה להשקיע" in handler(10000, None, None, "סכום בשקלים", None)
    assert "גבוה מהנטו" in handler(10000, None, None, "סכום בשקלים", 20000)
    assert store.list_salary_events(uid) == []


def test_monthly_report_with_partial_profile_lists_what_is_missing():
    store, uid = new_store()
    store.save_profile(uid, InvestorProfile(monthly_expenses=10000, liquid_savings=0))
    html = appmod.make_monthly_handler(store, uid)(20000, 0, 0, "סכום בשקלים", 5000)
    assert "קרן חירום" in html and "מה חסר בפרופיל" in html and "אופק השקעה" in html


def test_payslip_upload_fills_fields(monkeypatch):
    store, uid = new_store()
    doc = {"doc_type": "payslip", "period": "2026-10", "data": {}, "warnings": [],
           "summary": {"net_to_bank": 17200.0, "pension_monthly_total": 2100.0, "study_fund_monthly_total": 900.0}}
    monkeypatch.setattr(appmod, "read_document", lambda path, client, model: doc)
    net, pension, study, status = appmod.make_payslip_handler(store, uid)("slip.pdf")
    assert (net, pension, study) == (17200.0, 2100.0, 900.0) and "התלוש נקרא" in status
    assert len(store.list_documents(uid, "payslip")) == 1

    def not_a_payslip(path, client, model):
        raise ValueError("כרגע אפשר לקרוא רק תלושי שכר.")

    monkeypatch.setattr(appmod, "read_document", not_a_payslip)
    *_, status = appmod.make_payslip_handler(store, uid)("report.pdf")
    assert "רק תלושי שכר" in status and len(store.list_documents(uid, "payslip")) == 1


def test_three_stages_and_no_analysis_tab():
    from portfolio_copilot.ui import STAGES, stages_html
    assert [k for k, _ in STAGES] == ["intake", "picture", "monthly"]
    assert "ניתוח והדרכה" not in stages_html({})
    store, uid = new_store()
    demo, _ = appmod.build_demo(store, uid)
    texts = {str(getattr(b, attr, "")) for b in demo.blocks.values() for attr in ("label", "value")}
    assert "המשך לניהול חודשי" in texts and "3. ניהול חודשי" in texts
    assert not any("ניתוח והדרכה" in t or "נתח את המצב" in t for t in texts)
