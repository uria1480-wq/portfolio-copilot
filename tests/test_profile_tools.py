"""בניית פרופיל בשיחה (update_profile) והגבלות "לא מוכר" (add_restriction), עם מודל מדומה."""
import json

from test_agent_flow import Call, FakeClient, Msg  # קודם: מגדיר משתני סביבה לפני יבוא agent
from portfolio_copilot import agent
from portfolio_copilot.agent_tools import run_profile_tool, tool_specs
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile, apply_profile_update, merge_profile
from portfolio_copilot.tools import plan_trades

PRICES = {"ZIM": 20.0, "VT": 100.0, "BND": 70.0, "BIL": 90.0}


def fetch(symbol):
    return PRICES[symbol]


def complete_profile(**extra):
    return InvestorProfile(age=40, investment_horizon_years=20, recommended_risk_level="מאוזן",
                           risk_confirmed=True, monthly_deposit=1000, **extra)


def concentrated_store():
    """תיק שבו ZIM הוא 50% מהשווי, הרבה מעל תקרת ה-20%."""
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    s.upsert_holding(uid, "ZIM", 100)   # 2,000
    s.upsert_holding(uid, "VT", 20)     # 2,000
    return s, uid


def final(reply="בסדר"):
    """תשובה סופית של המודל: טקסט רגיל."""
    return Msg(content=reply)


def tool_results(fake_call):
    return [json.loads(m["content"]) for m in fake_call["messages"] if m["role"] == "tool"]


# ---------- בדיקה בקוד ----------
def test_valid_values_are_accepted():
    p, accepted, rejected = apply_profile_update(InvestorProfile(), {"age": "35", "investment_horizon_years": 15.0,
                                                                     "monthly_deposit": "1,500"})
    assert (p.age, p.investment_horizon_years, p.monthly_deposit) == (35, 15, 1500.0)
    assert set(accepted) == {"age", "investment_horizon_years", "monthly_deposit"} and rejected == {}


def test_invalid_values_are_rejected_with_reason_and_old_value_kept():
    start = InvestorProfile(age=30)
    p, accepted, rejected = apply_profile_update(start, {
        "age": 150, "investment_horizon_years": 0, "monthly_deposit": -5, "recommended_risk_level": "בינוני",
        "max_single_asset_weight": 0.01, "life_stage": "חייזר", "favorite_color": "כחול", "needs_cashflow": "כן",
    })
    assert accepted == {}
    assert set(rejected) == {"age", "investment_horizon_years", "monthly_deposit", "recommended_risk_level",
                             "max_single_asset_weight", "life_stage", "favorite_color", "needs_cashflow"}
    assert all(isinstance(r, str) and r for r in rejected.values())
    assert p == start


def test_bool_is_not_a_number_and_fraction_is_not_an_age():
    _, _, rejected = apply_profile_update(InvestorProfile(), {"age": True, "investment_horizon_years": 2.5})
    assert set(rejected) == {"age", "investment_horizon_years"}


def test_cannot_confirm_risk_without_level():
    p, _, rejected = apply_profile_update(InvestorProfile(), {"risk_confirmed": True})
    assert "risk_confirmed" in rejected and not p.risk_confirmed


def test_changing_risk_level_resets_confirmation():
    p, _, _ = apply_profile_update(complete_profile(), {"recommended_risk_level": "אגרסיבי"})
    assert p.recommended_risk_level == "אגרסיבי" and not p.risk_confirmed
    p, _, _ = apply_profile_update(p, {"recommended_risk_level": "שמרני", "risk_confirmed": True})
    assert p.risk_confirmed


def test_restrictions_cannot_be_set_through_update_profile():
    p, _, rejected = apply_profile_update(InvestorProfile(), {"no_sell_symbols": ["ZIM"], "restrictions": ["x"]})
    assert set(rejected) == {"no_sell_symbols", "restrictions"} and p.no_sell_symbols == []


def test_missing_fields_order_and_completion():
    assert InvestorProfile().missing_fields() == ["age", "investment_horizon_years", "recommended_risk_level",
                                                  "monthly_deposit"]
    assert InvestorProfile(life_stage="סטודנט", recommended_risk_level="מאוזן").missing_fields() == [
        "investment_horizon_years", "risk_confirmed", "monthly_deposit"]
    assert complete_profile().missing_fields() == []


def test_free_json_cannot_remove_no_sell():
    p = merge_profile(complete_profile(no_sell_symbols=["ZIM"]), {"no_sell_symbols": []})
    assert p.no_sell_symbols == ["ZIM"]


# ---------- אכיפה בקוד בחישוב ----------
def test_plan_trades_honors_profile_no_sell():
    holdings = [{"symbol": "ZIM", "quantity": 100}, {"symbol": "VT", "quantity": 20}]
    before = plan_trades(complete_profile(), holdings, PRICES, 1000, allow_sell=True)
    assert [s["symbol"] for s in before["sells"]] == ["ZIM"]
    after = plan_trades(complete_profile(no_sell_symbols=["ZIM"]), holdings, PRICES, 1000, allow_sell=True)
    assert after["sells"] == [] and after["kept_symbols"] == ["ZIM"]
    assert abs(sum(after["buys"].values()) - 1000) < 0.01


# ---------- הכלים עצמם ----------
def test_update_profile_tool_reports_next_field():
    result, p = run_profile_tool("update_profile", {"age": 28, "investment_horizon_years": -3}, InvestorProfile())
    assert result["accepted"] == {"age": 28}
    assert "investment_horizon_years" in result["rejected"]
    assert result["next_field"] == "investment_horizon_years" and result["complete"] is False
    assert p.age == 28


def test_add_restriction_rejects_bad_input_without_changing_profile():
    p = complete_profile()
    for args in ({"symbol": ""}, {"symbol": "צים בע\"מ"}, {"symbol": "ZIM", "kind": "no_buy"}):
        result, same = run_profile_tool("add_restriction", args, p)
        assert "error" in result and same == p


def test_add_restriction_saves_and_replans():
    s, uid = concentrated_store()
    result, p = run_profile_tool("add_restriction", {"symbol": " zim ", "allow_sell": True},
                                 complete_profile(), s, uid, fetch)
    assert p.no_sell_symbols == ["ZIM"] and "לא למכור: ZIM" in p.restrictions
    assert result["saved"] and result["replan"]["sells"] == []
    assert result["replan"]["kept_symbols"] == ["ZIM"]
    # הוספה חוזרת לא יוצרת כפילות
    _, p = run_profile_tool("add_restriction", {"symbol": "ZIM"}, p, s, uid, fetch)
    assert p.no_sell_symbols == ["ZIM"]


def test_add_restriction_without_complete_profile_skips_replan():
    s, uid = concentrated_store()
    result, p = run_profile_tool("add_restriction", {"symbol": "ZIM"}, InvestorProfile(), s, uid, fetch)
    assert p.no_sell_symbols == ["ZIM"] and result["replan"] is None


def test_profile_tools_are_exposed_to_model():
    names = {t["function"]["name"] for t in tool_specs(False)}
    assert {"update_profile", "add_restriction"} <= names


# ---------- הלולאה ב-chat_step ----------
def test_chat_step_updates_profile_inside_loop(monkeypatch):
    fake = FakeClient([
        Msg(tool_calls=[Call("c1", "update_profile", json.dumps({"age": 33, "investment_horizon_years": 500}))]),
        final("מה אופק ההשקעה שלך בשנים?"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = concentrated_store()
    reply, p = agent.chat_step([{"role": "user", "content": "אני בן 33 ומשקיע ל-500 שנה"}], InvestorProfile(), s, uid)

    assert p.age == 33 and p.investment_horizon_years is None
    [result] = tool_results(fake.calls[1])
    assert "investment_horizon_years" in result["rejected"]
    assert result["next_field"] == "investment_horizon_years"
    # הודעת "פרופיל נוכחי" עודכנה בתוך הלולאה, והפרופיל נשמר ב-store
    assert '"age":33' in fake.calls[1]["messages"][1]["content"]
    assert s.load_profile(uid).age == 33


def test_restriction_and_replan_in_same_turn(monkeypatch):
    """המשתמש אומר "אני לא מוכר את ZIM": ההגבלה נשמרת, ו-plan_deposit שרץ אחריה באותו תור מכבד אותה
    גם בלי שהמודל העביר keep_symbols."""
    fake = FakeClient([
        Msg(tool_calls=[Call("c1", "add_restriction", json.dumps({"symbol": "ZIM"}))]),
        Msg(tool_calls=[Call("c2", "plan_deposit", json.dumps({"amount": 1000, "allow_sell": True}))]),
        final("עדכנתי. ZIM לא יוצע למכירה"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = concentrated_store()
    reply, p = agent.chat_step([{"role": "user", "content": "אני לא מוכר את ZIM"}], complete_profile(),
                               s, uid, fetch=fetch)

    assert p.no_sell_symbols == ["ZIM"] and s.load_profile(uid).no_sell_symbols == ["ZIM"]
    plan = tool_results(fake.calls[2])[-1]
    assert plan["sells"] == [] and plan["kept_symbols"] == ["ZIM"]


def test_multi_turn_interview_until_complete(monkeypatch):
    s, uid = concentrated_store()
    turns = [
        ("אני בן 30", {"age": 30}, "investment_horizon_years"),
        ("ל-25 שנה", {"investment_horizon_years": 25, "recommended_risk_level": "אגרסיבי"}, "risk_confirmed"),
        ("מאשר את האגרסיבי", {"risk_confirmed": True}, "monthly_deposit"),
        ("2000 בחודש", {"monthly_deposit": 2000}, None),
    ]
    history, profile = [], InvestorProfile()
    for text, args, expected_next in turns:
        fake = FakeClient([Msg(tool_calls=[Call("c", "update_profile", json.dumps(args, ensure_ascii=False))]),
                           final("שאלה הבאה")])
        monkeypatch.setattr(agent, "client", fake)
        history.append({"role": "user", "content": text})
        reply, profile = agent.chat_step(history, profile, s, uid)
        history.append({"role": "assistant", "content": reply})
        [result] = tool_results(fake.calls[1])
        assert result["next_field"] == expected_next and result["rejected"] == {}

    assert result["complete"] and profile.is_complete() and profile.monthly_deposit == 2000
    assert s.load_profile(uid) == profile


def test_bad_final_json_keeps_tool_updates(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c1", "update_profile", '{"age": 50}')]), Msg(content="סתם טקסט")])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = concentrated_store()
    _, p = agent.chat_step([{"role": "user", "content": "בן 50"}], InvestorProfile(), s, uid)
    assert p.age == 50


def test_profile_in_final_json_is_ignored(monkeypatch):
    """רק הכלים מעדכנים את הפרופיל. profile ב-JSON הסופי לא נקרא, גם כשהוא סותר את הכלי."""
    sneaky = json.dumps({"reply": "קיבלתי", "profile": {"age": 99, "risk_confirmed": True,
                                                       "recommended_risk_level": "אגרסיבי"}}, ensure_ascii=False)
    fake = FakeClient([Msg(tool_calls=[Call("c1", "update_profile", '{"age": 50}')]), Msg(content=sneaky)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = concentrated_store()
    reply, p = agent.chat_step([{"role": "user", "content": "בן 50"}], InvestorProfile(), s, uid)
    assert reply == "קיבלתי"
    assert p.age == 50 and p.recommended_risk_level is None and not p.risk_confirmed
    assert s.load_profile(uid) == p


def test_each_round_prints_llm_time_and_tools(monkeypatch, capsys):
    fake = FakeClient([
        Msg(tool_calls=[Call("c1", "update_profile", '{"age": 50}'), Call("c2", "get_portfolio")]),
        final("בסדר"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = concentrated_store()
    agent.chat_step([{"role": "user", "content": "בן 50"}], InvestorProfile(), s, uid, fetch=fetch)
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[agent] round")]
    assert len(lines) == 2
    assert lines[0].startswith("[agent] round 1: LLM ") and "update_profile (" in lines[0] and "get_portfolio (" in lines[0]
    assert lines[1].startswith("[agent] round 2: LLM ") and "tools: none" in lines[1]
