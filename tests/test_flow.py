"""בדיקת המסע המלא דרך הפונקציות של הממשק: ראיון, תמונת מצב, ניתוח, אישור ומשכורת."""
import json
import os

import pytest

pytest.importorskip("gradio")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from types import SimpleNamespace

from portfolio_copilot import app as appmod
from portfolio_copilot.db import Store

FETCH = lambda symbol: 100.0
GUIDANCE = {"summary": "מצב יציב", "risk_level": "מאוזן", "risk_reasoning": "אופק בינוני",
            "steps": [{"title": "להפריש כל חודש", "why": "הרגל"}],
            "plan": {"savings_mode": "fixed", "savings_value": 10000, "rationale": "מתאים",
                     "buckets": [{"name": "קרן חירום", "kind": "cash", "share": 0.3}, {"name": "השקעות", "kind": "invest", "share": 0.7}]}}


def llm(content):
    msg = SimpleNamespace(content=content)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=msg)]))))


def fill_intake(store, uid, **override):
    values = dict(age=35, status="שכיר/ה", income=40000, expenses=15000, can_save=10000, liquid=60000, debt=0,
                  goals=["פרישה"], horizon="7 עד 15 שנים", reaction="לא אעשה כלום ואחכה", experience="קצת ניסיון",
                  max_weight="עד 20%", restrictions="לא מוכר צים")
    values.update(override)
    return appmod.make_intake_handler(store, uid, FETCH)(*values.values())


def test_full_journey():
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    assert not any(appmod.stage_flags(store, uid).values())

    # 1. ראיון: חסר מידע לא נשמר כהשלמה, ומלא מקדם לשלב הבא
    out = fill_intake(store, uid, age=None)
    assert "חסר מידע" in out[0] and not appmod.stage_flags(store, uid)["intake"]
    out = fill_intake(store, uid)
    assert "רמת סיכון מוצעת: מאוזן" in out[0] and appmod.stage_flags(store, uid)["intake"]
    profile = store.load_profile(uid)
    assert profile.age == 35 and profile.restrictions == ["לא מוכר צים"] and not profile.risk_confirmed

    # 2. המצב שלי: ערכים ידניים, החזקות ומסמך נכנסים לתמונה אחת
    appmod.make_assets_handler(store, uid, FETCH)(150000, 40000, None)
    store.upsert_holding(uid, "VT", 100)
    store.save_document(uid, {"doc_type": "fund_report", "period": "2026-Q1", "data": {}, "warnings": [],
                              "summary": {"fund_type": "pension", "fund_name": "קרן", "provider": "חברה", "balance_end": 200000.0}})
    pic = appmod.compute_picture(store, uid, FETCH)
    values = {i["label"]: i["value"] for i in pic["items"]}
    assert values["קרן פנסיה"] == 200000 and values["קרן השתלמות"] == 40000 and values["תיק השקעות"] == 10000.0
    assert appmod.stage_flags(store, uid)["picture"]

    # 3. ניתוח ואישור
    analysis = appmod.make_analysis_handler(store, uid, llm(json.dumps(GUIDANCE, ensure_ascii=False)), "m", FETCH)()
    assert "מצב יציב" in analysis[0] and analysis[1] == "מאוזן" and analysis[3] == 10000
    assert appmod.stage_flags(store, uid)["analysis"] and not appmod.stage_flags(store, uid)["monthly"]
    confirm = appmod.make_confirm_handler(store, uid)("מאוזן", "סכום קבוע בשקלים", 10000, 30, 40000)
    assert "התוכנית אושרה" in confirm[0]
    assert store.load_plan(uid).is_ready() and store.load_profile(uid).is_complete()
    assert appmod.stage_flags(store, uid) == {"intake": True, "picture": True, "analysis": True, "monthly": True}

    # 4. ניהול חודשי: נכנסה משכורת
    html = appmod.make_salary_handler(store, uid, FETCH)(40000, 4000, 2500)
    assert "מה לעשות עם ₪10,000" in html and "העבר" in html and "קנה" in html and "₪16,500" in html
    assert len(store.list_salary_events(uid)) == 1


def test_analysis_before_interview_is_blocked_and_confirm_needs_a_risk_level():
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    out = appmod.make_analysis_handler(store, uid, llm("{}"), "m", FETCH)()
    assert "השלם קודם את הראיון" in out[0]
    fill_intake(store, uid)
    assert "בחר רמת סיכון" in appmod.make_confirm_handler(store, uid)(None, "סכום קבוע בשקלים", 1000, 30, None)[0]
    assert "הזן סכום" in appmod.make_confirm_handler(store, uid)("מאוזן", "סכום קבוע בשקלים", None, 30, None)[0]


def test_model_failure_still_leads_to_a_usable_plan():
    store = Store(":memory:")
    uid = store.get_or_create_user("demo")
    fill_intake(store, uid)
    out = appmod.make_analysis_handler(store, uid, llm("לא JSON"), "m", FETCH)()
    assert "ניתוח בסיסי" in out[0] and out[3] == 10000