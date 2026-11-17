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


def test_holding_upsert_updates_instead_of_duplicating():
    s = Store(":memory:")
    uid = s.get_or_create_user("uria")
    s.upsert_holding(uid, "zim", 100, 20.5)
    s.upsert_holding(uid, "ZIM", 150, 21.0)
    assert s.list_holdings(uid) == [{"symbol": "ZIM", "quantity": 150, "avg_cost": 21.0}]
    s.delete_holding(uid, "zim")
    assert s.list_holdings(uid) == []


def test_users_are_isolated():
    s = Store(":memory:")
    a, b = s.get_or_create_user("a"), s.get_or_create_user("b")
    s.upsert_holding(a, "SPY", 5)
    s.add_deposit(a, 1000)
    assert s.list_holdings(b) == [] and s.list_deposits(b) == []


def test_deposits_ordered_and_data_survives_reopen(tmp_path):
    path = tmp_path / "p.db"
    s = Store(path)
    uid = s.get_or_create_user("uria")
    s.add_deposit(uid, 500, "ינואר", "2026-01-01")
    s.add_deposit(uid, 700, "פברואר", "2026-02-01")
    s.close()
    s2 = Store(path)
    assert [d["amount"] for d in s2.list_deposits(s2.get_or_create_user("uria"))] == [500, 700]