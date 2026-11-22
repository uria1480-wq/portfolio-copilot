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


def test_fresh_flag_uses_memory_store_and_default_uses_file(monkeypatch):
    """בודק את שני המצבים בלי לפתוח את הקובץ האמיתי ובלי להפעיל את השרת."""
    paths, launched = [], []

    def fake_store(path="data/portfolio.db"):
        paths.append(path)
        return Store(":memory:")  # לא נוגעים ב-data/portfolio.db אמיתי

    fake_demo = SimpleNamespace(launch=lambda **kw: launched.append(kw))
    monkeypatch.setattr(appmod, "Store", fake_store)
    monkeypatch.setattr(appmod, "build_demo", lambda store, uid: (fake_demo, {}))

    appmod.main(["--fresh"])
    appmod.main([])
    assert paths == [":memory:", "data/portfolio.db"] and len(launched) == 2
    assert appmod.parse_args(["--fresh"]).fresh and not appmod.parse_args([]).fresh
    assert all(kw["share"] is False and "auth" not in kw for kw in launched)  # ברירת מחדל: מקומי בלבד


def fake_launch(monkeypatch):
    launched = []
    monkeypatch.setattr(appmod, "Store", lambda path="data/portfolio.db": Store(":memory:"))
    monkeypatch.setattr(appmod, "build_demo",
                        lambda store, uid: (SimpleNamespace(launch=lambda **kw: launched.append(kw)), {}))
    return launched


def test_share_flag_reads_password_and_username_from_env(monkeypatch):
    launched = fake_launch(monkeypatch)
    monkeypatch.setenv("SHARE_PASSWORD", "from-env-secret")
    monkeypatch.setenv("SHARE_USERNAME", "team")
    appmod.main(["--fresh", "--share"])
    assert launched == [{"share": True, "auth": ("team", "from-env-secret")}]


def test_share_without_username_uses_default(monkeypatch):
    monkeypatch.delenv("SHARE_USERNAME", raising=False)
    assert appmod.share_settings(True, {"SHARE_PASSWORD": "x"}) == {"share": True, "auth": ("family", "x")}
    assert appmod.share_settings(False, {"SHARE_PASSWORD": "x"}) == {"share": False}


@pytest.mark.parametrize("password", [None, "", "   "])
def test_share_without_password_refuses_to_start(monkeypatch, password):
    launched = fake_launch(monkeypatch)
    if password is None:
        monkeypatch.delenv("SHARE_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("SHARE_PASSWORD", password)
    with pytest.raises(SystemExit) as e:
        appmod.main(["--fresh", "--share"])
    assert "SHARE_PASSWORD" in str(e.value) and launched == []


def test_no_password_is_written_in_app_code():
    source = open(appmod.__file__, encoding="utf-8").read()
    assert "u12345" not in source and "share=True" not in source


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
    assert "מה לעשות עם ₪10,000" in html and "25% מהנטו שלך (₪40,000)" in html
    assert "מדד מניות ארה&quot;ב" in html and "₪2,750" in html and "קרן חירום (" not in html
    assert "מכירה" in html and "קנה" not in html  # "אין הצעות מכירה", בלי פעולות קנייה של נכס ספציפי
    event = store.list_salary_events(uid)[0]
    assert (event["net"], event["set_aside"], event["period"]) == (40000, 10000, event["allocation"]["as_of"][:7])


def test_monthly_report_errors_are_shown_and_nothing_is_saved():
    store, uid = new_store()
    store.save_profile(uid, complete_profile())
    handler = appmod.make_monthly_handler(store, uid)
    assert "הזן כמה נכנס נטו" in handler(None, None, None, "סכום קבוע בשקלים", 1000)
    assert "הזן כמה להשקיע" in handler(10000, None, None, "סכום קבוע בשקלים", None)
    assert "גבוה מהנטו" in handler(10000, None, None, "סכום קבוע בשקלים", 20000)
    assert store.list_salary_events(uid) == []


def test_monthly_report_with_partial_profile_lists_what_is_missing():
    store, uid = new_store()
    store.save_profile(uid, InvestorProfile(monthly_expenses=10000, liquid_savings=0))
    html = appmod.make_monthly_handler(store, uid)(20000, 0, 0, "סכום קבוע בשקלים", 5000)
    assert "קרן חירום" in html and "מה חסר בפרופיל" in html and "אופק השקעה" in html


def test_payslip_upload_fills_fields(monkeypatch):
    store, uid = new_store()
    doc = {"doc_type": "payslip", "period": "2026-10", "data": {}, "warnings": [],
           "summary": {"net_to_bank": 17200.0, "pension_monthly_total": 2100.0, "study_fund_monthly_total": 900.0}}
    monkeypatch.setattr(appmod, "read_payslip", lambda path: doc)
    net, pension, study, status = appmod.make_payslip_handler(store, uid)("slip.pdf")
    assert (net, pension, study) == (17200.0, 2100.0, 900.0) and "התלוש נקרא" in status
    assert store.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1

    def not_a_payslip(path):
        raise ValueError("כרגע אפשר לקרוא רק תלושי שכר.")

    monkeypatch.setattr(appmod, "read_payslip", not_a_payslip)
    *_, status = appmod.make_payslip_handler(store, uid)("report.pdf")
    assert "רק תלושי שכר" in status and store.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_three_stages_and_no_analysis_tab():
    from portfolio_copilot.ui import STAGES, stages_html
    assert [k for k, _ in STAGES] == ["intake", "picture", "monthly"]
    assert "ניתוח והדרכה" not in stages_html({})
    store, uid = new_store()
    demo, _ = appmod.build_demo(store, uid)
    texts = {str(getattr(b, attr, "")) for b in demo.blocks.values() for attr in ("label", "value")}
    assert "המשך לניהול חודשי" in texts and "3. ניהול חודשי" in texts
    assert "יש לי שאלה? דבר עם הסוכן" in texts
    assert not any("ניתוח והדרכה" in t or "נתח את המצב" in t for t in texts)


# ---------- ברירות מחדל, קרן חירום מצטברת ונשואים ----------
def component(demo, label):
    return next(b for b in demo.blocks.values() if getattr(b, "label", None) == label)


def test_default_percent_comes_from_interview_and_user_can_change_it():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(liquid_savings=100000))  # 10,000 מתוך 40,000 = 25%
    demo, _ = appmod.build_demo(store, uid)
    assert component(demo, appmod.AMOUNT_LABEL).value == 25.0
    assert component(demo, "כמה להשקיע החודש").value == "אחוז מהנטו"
    mode, value, *_ = appmod.make_monthly_defaults_handler(store, uid)()
    assert mode["value"] == "אחוז מהנטו" and value["value"] == 25.0 and "אפשר לשנות" in value["info"]
    html = appmod.make_monthly_handler(store, uid)(40000, 0, 0, "אחוז מהנטו", 10)  # המשתמש שינה ל-10%
    assert "מה לעשות עם ₪4,000" in html


def test_no_default_percent_when_interview_has_no_values():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(monthly_deposit=None))
    demo, _ = appmod.build_demo(store, uid)
    assert component(demo, appmod.AMOUNT_LABEL).value is None
    value = appmod.make_monthly_defaults_handler(store, uid)()[1]
    assert value["value"] is None and value["info"].startswith("השדה ריק")


def test_default_percent_for_partnered_uses_combined_interview_net():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="נשוי", spouse_monthly_net_income=40000))
    value = appmod.make_monthly_defaults_handler(store, uid)()[1]  # 10,000 מתוך 80,000
    assert value["value"] == 12.5 and "משותף" in value["info"]


def test_emergency_fund_is_not_requested_again_every_month():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(monthly_expenses=10000, liquid_savings=30000))  # חוסר 30,000
    run = appmod.make_monthly_handler(store, uid)
    for _ in range(6):
        run(40000, 0, 0, "סכום קבוע בשקלים", 5000)
    events = store.list_salary_events(uid)
    assert [e["allocation"]["emergency_amount"] for e in reversed(events)] == [5000] * 6
    html = run(40000, 0, 0, "סכום קבוע בשקלים", 5000)  # חודש 7: החוסר מולא
    assert store.list_salary_events(uid)[0]["allocation"]["emergency_amount"] == 0
    assert "קרן החירום מלאה" in html


def test_emergency_history_counts_more_than_twelve_reports():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(monthly_expenses=10000, liquid_savings=0))  # חוסר 60,000
    run = appmod.make_monthly_handler(store, uid)
    for _ in range(13):
        run(40000, 0, 0, "סכום קבוע בשקלים", 4000)  # 13 x 4,000 = 52,000
    run(40000, 0, 0, "סכום קבוע בשקלים", 10000)
    assert store.list_salary_events(uid)[0]["allocation"]["emergency_amount"] == 8000


def test_single_does_not_see_partner_fields_and_married_does():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="רווק"))
    demo, _ = appmod.build_demo(store, uid)
    assert not component(demo, "נטו בן/בת הזוג החודש (₪, לא חובה)").visible
    assert not component(demo, "תלוש של בן/בת הזוג PDF (לא חובה)").visible
    store.save_profile(uid, complete_profile(marital_status="נשוי", spouse_monthly_net_income=15000))
    demo, _ = appmod.build_demo(store, uid)
    assert component(demo, "נטו בן/בת הזוג החודש (₪, לא חובה)").visible
    *_, net_visible, slip_visible = appmod.make_monthly_defaults_handler(store, uid)()
    assert net_visible["visible"] and slip_visible["visible"]


def test_married_monthly_report_with_and_without_partner_net():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="נשוי", spouse_monthly_net_income=15000,
                                             liquid_savings=100000))
    run = appmod.make_monthly_handler(store, uid)
    own = run(40000, 0, 0, "אחוז מהנטו", 10)
    assert "מה לעשות עם ₪4,000" in own and "נטו שלך" in own
    both = run(40000, 0, 0, "אחוז מהנטו", 10, 20000)
    assert "מה לעשות עם ₪6,000" in both and "נטו משותף" in both and "נטו: שלך · בן/בת הזוג · משותף" in both
    assert store.list_salary_events(uid)[0]["partner_net"] == 20000
    assert store.load_profile(uid).spouse_monthly_net_income == 15000  # לא נשמר בפרופיל


def test_partner_payslip_fills_partner_net_and_rejects_non_payslip(monkeypatch):
    store, uid = new_store()
    slip = {"doc_type": "payslip", "period": "2026-10", "data": {}, "warnings": [],
            "summary": {"net_to_bank": 15500.0, "pension_monthly_total": 1900.0, "study_fund_monthly_total": 700.0}}
    monkeypatch.setattr(appmod, "read_payslip", lambda path: slip)
    net, pension, study, status = appmod.make_payslip_handler(store, uid, appmod.PARTNER_PAYSLIP_OK)("partner.pdf")
    assert (net, pension, study) == (15500.0, 1900.0, 700.0) and "בן/בת הזוג נקרא" in status

    def not_a_payslip(path):
        raise ValueError("כרגע אפשר לקרוא רק תלושי שכר.")

    monkeypatch.setattr(appmod, "read_payslip", not_a_payslip)
    *_, status = appmod.make_payslip_handler(store, uid, appmod.PARTNER_PAYSLIP_OK)("report.pdf")
    assert "רק תלושי שכר" in status


# ---------- פנסיה והשתלמות של בן/בת הזוג ----------
PARTNER_LABELS = ("נטו בן/בת הזוג החודש (₪, לא חובה)", "פנסיה בן/בת הזוג החודש (₪, לא חובה)",
                  "השתלמות בן/בת הזוג החודש (₪, לא חובה)", "תלוש של בן/בת הזוג PDF (לא חובה)")


def test_partner_pension_and_study_fields_only_for_partnered():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="רווק"))
    demo, _ = appmod.build_demo(store, uid)
    assert not any(component(demo, label).visible for label in PARTNER_LABELS)
    assert not any(u["visible"] for u in appmod.make_monthly_defaults_handler(store, uid)()[2:])
    store.save_profile(uid, complete_profile(marital_status="ידוע בציבור", spouse_monthly_net_income=15000))
    demo, _ = appmod.build_demo(store, uid)
    assert all(component(demo, label).visible for label in PARTNER_LABELS)
    assert all(u["visible"] for u in appmod.make_monthly_defaults_handler(store, uid)()[2:])


def test_married_with_partner_values_saves_own_partner_and_combined():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="נשוי", spouse_monthly_net_income=15000,
                                             liquid_savings=100000))
    html = appmod.make_monthly_handler(store, uid)(20000, 2000, 800, "אחוז מהנטו", 10, 15000, 1500, 600)
    assert "מה לעשות עם ₪3,500" in html and "נטו משותף" in html
    e = store.list_salary_events(uid)[0]
    assert (e["net"], e["partner_net"], e["household_net"]) == (20000, 15000, 35000)
    assert (e["pension_contributions"], e["partner_pension"], e["total_pension"]) == (2000, 1500, 3500)
    assert (e["study_fund_contributions"], e["partner_study_fund"], e["total_study_fund"]) == (800, 600, 1400)
    assert e["total_saved_this_month"] == 3500 + 3500 + 1400


def test_married_without_partner_values_uses_own_only():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="נשוי", spouse_monthly_net_income=15000,
                                             liquid_savings=100000))
    appmod.make_monthly_handler(store, uid)(20000, 2000, 800, "אחוז מהנטו", 10, None, None, None)
    e = store.list_salary_events(uid)[0]
    assert (e["household_net"], e["total_pension"], e["total_study_fund"], e["set_aside"]) == (20000, 2000, 800, 2000)
    assert e["partner_net"] is None and e["partner_pension"] is None and e["percent_base"] == "נטו שלך"


# ---------- טבלת ההיסטוריה ----------
def test_history_table_shows_combined_amounts():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="נשוי", spouse_monthly_net_income=15000,
                                             monthly_expenses=10000, liquid_savings=25000))  # יעד 3 חודשים (שכיר + בן/בת זוג מכניס/ה) = 30,000, חוסר 5,000
    html = appmod.make_monthly_handler(store, uid)(20000, 2000, 800, "סכום קבוע בשקלים", 7000, 15000, 1500, 600)
    history = html[html.index("<h3>היסטוריה</h3>"):]
    for header in ("נטו משותף", "פנסיה", "השתלמות", "הופקד", "מזה לקרן חירום"):
        assert f"<th>{header}</th>" in history
    row = history[history.index("<td>"):]
    assert "₪35,000" in row and "₪3,500" in row and "₪1,400" in row and "₪7,000" in row and "₪5,000" in row
    assert "₪20,000" not in row  # הנטו שלך לבד לא מוצג בטבלה


def test_deposit_above_combined_net_is_rejected_also_with_partner():
    store, uid = new_store()
    store.save_profile(uid, complete_profile(marital_status="נשוי", spouse_monthly_net_income=15000))
    run = appmod.make_monthly_handler(store, uid)
    assert "גבוה מהנטו משותף" in run(20000, 0, 0, "סכום קבוע בשקלים", 35000.01, 15000, None, None)
    assert "גבוה מהנטו שלך" in run(20000, 0, 0, "סכום קבוע בשקלים", 20000.01, None, None, None)
    assert store.list_salary_events(uid) == []
    assert "מה לעשות עם ₪35,000" in run(20000, 0, 0, "סכום קבוע בשקלים", 35000, 15000, None, None)


def test_history_reads_old_records_without_combined_fields():
    from portfolio_copilot.ui import salary_history_html
    html = salary_history_html([{"period": "2026-01", "net": 9000.0, "set_aside": 1000.0}])
    assert "₪9,000" in html and "₪1,000" in html and "—" in html



# ---------- הדשבורד מתעדכן אחרי דיווח ----------
def test_dashboard_updates_after_monthly_report_and_profile_stays():
    store, uid = new_store()
    profile = complete_profile(marital_status="נשוי", spouse_monthly_net_income=15000, liquid_savings=100000)
    store.save_profile(uid, profile)
    refresh = appmod.make_refresh_handler(store, uid)
    before = refresh()[0]
    assert "₪100,000" in before and "דיווח חודשי" not in before
    run = appmod.make_monthly_handler(store, uid)
    run(20000, 2000, 800, "סכום קבוע בשקלים", 3000, 15000, 1500, 600)
    run(20000, 2000, 800, "סכום קבוע בשקלים", 3000, None, None, None)
    after = refresh()[0]
    assert "₪106,000" in after and "₪100,000 מהראיון + ₪6,000 מדיווחים חודשיים" in after
    assert "₪200,000 מהראיון + ₪5,500 מדיווחים חודשיים" in after  # פנסיה: 3,500 + 2,000
    assert "₪40,000 מהראיון + ₪2,200 מדיווחים חודשיים" in after   # השתלמות: 1,400 + 800
    assert store.load_profile(uid) == profile


def test_proposal_says_it_uses_interview_state():
    store, uid = new_store()
    store.save_profile(uid, complete_profile())
    assert "לפי המצב שהוזן בראיון" in appmod.make_proposal_handler(store, uid)()


def test_report_button_refreshes_dashboard():
    store, uid = new_store()
    demo, _ = appmod.build_demo(store, uid)
    by_id = {b._id: b for b in demo.blocks.values()}
    button = next(b for b in demo.blocks.values() if getattr(b, "value", None) == "חשב חלוקה")
    chain = [d for d in demo.config["dependencies"] if any(t[0] == button._id for t in d.get("targets", []))]
    assert chain, "הכפתור לא מחובר"
    refresh_steps = [d for d in demo.config["dependencies"]
                     if d.get("trigger_after") == demo.config["dependencies"].index(chain[0])]
    labels = {by_id[o].__class__.__name__ for d in refresh_steps for o in d["outputs"]}
    assert refresh_steps and labels == {"HTML"}


def test_app_does_not_see_llm_client_or_model_name():
    """קריאות ל-LLM מוסתרות מאחורי ממשק בשמות של התחום (CLAUDE.md)."""
    assert not hasattr(appmod, "client") and not hasattr(appmod, "MODEL_NAME")
    assert not hasattr(appmod, "read_document")


def test_read_payslip_passes_agent_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(agent, "read_document", lambda path, client, model: seen.update(
        path=path, client=client, model=model) or {"ok": True})
    assert agent.read_payslip("slip.pdf") == {"ok": True}
    assert seen == {"path": "slip.pdf", "client": agent.client, "model": agent.MODEL_NAME}


def test_utf8_console_lets_hebrew_print_on_cp1252_stream():
    import io

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    appmod.utf8_console(stream)
    print("[app] --fresh: מסד נתונים בזיכרון", file=stream)
    stream.flush()
    assert "מסד נתונים".encode("utf-8") in raw.getvalue()
    appmod.utf8_console(object())  # זרם בלי reconfigure לא נשבר


def test_console_script_points_to_app_main():
    import tomllib
    from importlib import import_module
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    module, func = pyproject["project"]["scripts"]["portfolio-copilot"].split(":")
    assert getattr(import_module(module), func) is appmod.main


def test_gemini_smoke_script_is_not_collected_by_pytest():
    from pathlib import Path

    root = Path(__file__).parents[1]
    assert not (root / "test_gemini.py").exists()
    assert not list((root / "scripts").glob("test_*.py"))


@pytest.mark.parametrize("message", [appmod.PAYSLIP_OK, appmod.PARTNER_PAYSLIP_OK])
def test_payslip_warnings_are_shown_under_the_reading_result(monkeypatch, message):
    store, uid = new_store()
    warnings = ["ברוטו פחות ניכויי חובה לא שווה לנטו", "חודש התלוש לא בפורמט YYYY-MM"]
    doc = {"doc_type": "payslip", "period": "2026-10", "data": {}, "warnings": warnings,
           "summary": {"net_to_bank": 17200.0, "pension_monthly_total": 2100.0, "study_fund_monthly_total": 900.0}}
    monkeypatch.setattr(appmod, "read_payslip", lambda path: doc)
    net, *_, status = appmod.make_payslip_handler(store, uid, message)("slip.pdf")
    assert net == 17200.0  # השדות עדיין מתמלאים, והמשתמש מחליט אם לתקן
    assert status.index("נקרא") < status.index("בדיקת החשבון בתלוש מצאה פערים")
    assert all(w in status for w in warnings) and "pc-banner-warn" in status


def test_payslip_without_warnings_shows_no_warning_box(monkeypatch):
    store, uid = new_store()
    doc = {"doc_type": "payslip", "period": "2026-10", "data": {}, "warnings": [],
           "summary": {"net_to_bank": 1.0, "pension_monthly_total": None, "study_fund_monthly_total": None}}
    monkeypatch.setattr(appmod, "read_payslip", lambda path: doc)
    *_, status = appmod.make_payslip_handler(store, uid)("slip.pdf")
    assert "pc-banner-warn" not in status and "התלוש נקרא" in status


def test_payslip_warnings_are_escaped():
    from portfolio_copilot.ui import payslip_status_html

    html = payslip_status_html(appmod.PAYSLIP_OK, ["<b>x</b>"])
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html

