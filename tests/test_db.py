from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile, merge_profile


def test_user_is_created_once():
    s = Store(":memory:")
    assert s.get_or_create_user("uria") == s.get_or_create_user("uria")
    assert s.get_or_create_user("eyal") != s.get_or_create_user("uria")


def test_profile_roundtrip_keeps_restrictions_and_confirmation():
    s = Store(":memory:")
    uid = s.get_or_create_user("uria")
    p = merge_profile(InvestorProfile(), {"age": 25, "restrictions": ["לא מוכר מניית צים"],
                                          "recommended_risk_level": "מאוזן", "risk_confirmed": True})
    s.save_profile(uid, p)
    loaded = s.load_profile(uid)
    assert loaded == p and loaded.risk_confirmed


def test_missing_profile_returns_empty_profile():
    s = Store(":memory:")
    assert s.load_profile(s.get_or_create_user("new")) == InvestorProfile()


def test_users_are_isolated():
    s = Store(":memory:")
    a, b = s.get_or_create_user("a"), s.get_or_create_user("b")
    s.save_profile(a, InvestorProfile(age=30))
    s.add_salary_event(a, {"period": "2026-11", "net": 1000.0})
    assert s.load_profile(b) == InvestorProfile() and s.list_salary_events(b) == []


def test_salary_events_newest_first_and_survive_reopen(tmp_path):
    path = tmp_path / "p.db"
    s = Store(path)
    uid = s.get_or_create_user("uria")
    for net in (1000.0, 2000.0):
        s.add_salary_event(uid, {"period": "2026-11", "net": net})
    s.close()
    s2 = Store(path)
    assert [e["net"] for e in s2.list_salary_events(s2.get_or_create_user("uria"))] == [2000.0, 1000.0]


def test_old_saved_profile_is_cleaned_on_load_and_next_save():
    """פרופיל מגרסה קודמת: "לא למכור: X" ו-no_sell_symbols נעלמים בטעינה, בלי שגיאה. "לא לקנות" נשאר."""
    import json

    s = Store(":memory:")
    uid = s.get_or_create_user("old")
    old = {"age": 40, "no_sell_symbols": ["ZIM"], "no_buy_symbols": ["TSLA"],
           "restrictions": ["לא למכור: ZIM", "לא לקנות: TSLA", "בלי נשק"]}
    s.conn.execute("INSERT INTO profiles VALUES (?, ?, '2026-01-01')", (uid, json.dumps(old, ensure_ascii=False)))

    p = s.load_profile(uid)
    assert p.restrictions == ["לא לקנות: TSLA", "בלי נשק"] and p.no_buy_symbols == ["TSLA"]
    assert "no_sell_symbols" not in p.model_dump()

    s.save_profile(uid, p)
    raw = s.conn.execute("SELECT data_json FROM profiles WHERE user_id = ?", (uid,)).fetchone()[0]
    assert "no_sell_symbols" not in raw and "לא למכור" not in raw and "לא לקנות: TSLA" in raw
