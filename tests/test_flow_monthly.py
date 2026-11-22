"""זרימת הניהול החודשי: דיווח, תלוש ואזהרות, ברירות מחדל, קרן חירום מצטברת, זוגות, היסטוריה ודשבורד."""
import os

import pytest

pytest.importorskip("gradio")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from test_flow_interview import complete_profile, new_store

from portfolio_copilot import app as appmod
from portfolio_copilot.schemas import InvestorProfile


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
