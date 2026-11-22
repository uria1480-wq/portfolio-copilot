"""בניית פרופיל בשיחה (update_profile) והגבלות "אל תקנה" (add_restriction), עם מודל מדומה."""
import json
from datetime import date

from test_agent_flow import Call, FakeClient, Msg  # קודם: מגדיר משתני סביבה לפני יבוא agent
from portfolio_copilot import agent
from portfolio_copilot.agent_tools import run_profile_tool, tool_specs
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile, apply_profile_update, merge_profile


# תמונת מצב פיננסית מלאה מהראיון (תרחיש 2)
FINANCE = dict(marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=15000, monthly_expenses=9000, liquid_savings=40000,
               monthly_debt_payments=0, pension_balance=120000, study_fund_balance=30000, other_assets=0,
               investment_goal="דירה")

INTERVIEW_ORDER = ["age", "marital_status", "employment_status", "monthly_net_income", "monthly_expenses", "monthly_deposit",
                   "liquid_savings", "monthly_debt_payments", "pension_balance", "study_fund_balance", "other_assets",
                   "investment_goal", "investment_horizon_years", "recommended_risk_level"]


def complete_profile(**extra):
    return InvestorProfile(**{"age": 40, "investment_horizon_years": 20, "recommended_risk_level": "מאוזן",
                              "risk_confirmed": True, "monthly_deposit": 1000, **FINANCE, **extra})


def concentrated_store():
    s = Store(":memory:")
    return s, s.get_or_create_user("demo")


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
        "life_stage": "חייזר", "favorite_color": "כחול", "needs_cashflow": "כן",
    })
    assert accepted == {}
    assert set(rejected) == {"age", "investment_horizon_years", "monthly_deposit", "recommended_risk_level",
                             "life_stage", "favorite_color", "needs_cashflow"}
    assert all(isinstance(r, str) and r for r in rejected.values())
    assert p == start


def test_bool_is_not_a_number_and_fraction_is_not_an_age():
    _, _, rejected = apply_profile_update(InvestorProfile(), {"age": True, "investment_horizon_years": 2.5})
    assert set(rejected) == {"age", "investment_horizon_years"}


TODAY = date(2026, 11, 19)


def test_target_year_sets_horizon_computed_in_code():
    p, accepted, rejected = apply_profile_update(InvestorProfile(), {"target_year": 2029}, today=TODAY)
    assert p.investment_horizon_years == 3 and rejected == {}
    assert accepted == {"target_year": 2029, "investment_horizon_years": 3}


def test_past_target_year_is_rejected_with_reason():
    start = InvestorProfile(investment_horizon_years=10)
    p, accepted, rejected = apply_profile_update(start, {"target_year": 2026}, today=TODAY)
    assert accepted == {} and p == start
    assert "2026" in rejected["target_year"] and "לא בעתיד" in rejected["target_year"]


def test_too_far_target_year_is_rejected_with_reason():
    p, accepted, rejected = apply_profile_update(InvestorProfile(), {"target_year": 2107}, today=TODAY)
    assert accepted == {} and p.investment_horizon_years is None
    assert "רחוקה מדי" in rejected["target_year"] and "80" in rejected["target_year"]


def test_target_year_80_years_ahead_is_the_limit():
    p, _, rejected = apply_profile_update(InvestorProfile(), {"target_year": 2106}, today=TODAY)
    assert p.investment_horizon_years == 80 and rejected == {}


def test_target_year_must_be_whole_number():
    _, _, rejected = apply_profile_update(InvestorProfile(), {"target_year": "בקרוב"}, today=TODAY)
    assert "target_year" in rejected


def test_update_profile_tool_passes_date_and_spec_has_target_year():
    result, p = run_profile_tool("update_profile", {"target_year": 2029}, InvestorProfile(), today=TODAY)
    assert p.investment_horizon_years == 3 and result["accepted"]["investment_horizon_years"] == 3
    fn = next(t for t in tool_specs() if t["function"]["name"] == "update_profile")["function"]
    assert "target_year" in fn["parameters"]["properties"] and "target_year" in fn["description"]


def test_cannot_confirm_risk_without_level():
    p, _, rejected = apply_profile_update(InvestorProfile(), {"risk_confirmed": True})
    assert "risk_confirmed" in rejected and not p.risk_confirmed


def test_changing_risk_level_resets_confirmation():
    p, _, _ = apply_profile_update(complete_profile(), {"recommended_risk_level": "אגרסיבי"})
    assert p.recommended_risk_level == "אגרסיבי" and not p.risk_confirmed
    p, _, _ = apply_profile_update(p, {"recommended_risk_level": "שמרני", "risk_confirmed": True})
    assert p.risk_confirmed


def test_restrictions_cannot_be_set_through_update_profile():
    p, _, rejected = apply_profile_update(InvestorProfile(), {"no_buy_symbols": ["ZIM"], "restrictions": ["x"]})
    assert set(rejected) == {"no_buy_symbols", "restrictions"} and p.no_buy_symbols == []


def test_missing_fields_order_and_completion():
    assert InvestorProfile().missing_fields() == INTERVIEW_ORDER
    p = InvestorProfile(life_stage="סטודנט", recommended_risk_level="מאוזן", **FINANCE)
    assert p.missing_fields() == ["monthly_deposit", "investment_horizon_years", "risk_confirmed"]
    assert complete_profile().missing_fields() == []


def test_financial_fields_do_not_block_calculations():
    """is_complete (החישובים) לא תלוי בשדות הפיננסיים, רק הראיון כן."""
    p = InvestorProfile(age=40, investment_horizon_years=20, recommended_risk_level="מאוזן", risk_confirmed=True)
    assert p.is_complete() and "employment_status" in p.missing_fields()


def test_free_json_cannot_remove_no_buy():
    p = merge_profile(complete_profile(no_buy_symbols=["ZIM"]), {"no_buy_symbols": []})
    assert p.no_buy_symbols == ["ZIM"]


def test_free_json_cannot_change_unknown_fields():
    p = merge_profile(InvestorProfile(unknown_fields=["pension_balance"]), {"unknown_fields": ["age"]})
    assert p.unknown_fields == ["pension_balance"]


def test_profile_saved_before_new_fields_still_loads():
    old_json = '{"age": 30, "recommended_risk_level": "מאוזן", "risk_confirmed": true, "restrictions": []}'
    p = InvestorProfile.model_validate_json(old_json)
    assert p.monthly_net_income is None and p.unknown_fields == [] and p.missing_fields()[0] == "marital_status"


# ---------- תמונת מצב פיננסית: ערכים, "לא יודע" ו"אין" ----------
def test_financial_values_are_validated_in_code():
    p, accepted, rejected = apply_profile_update(InvestorProfile(), {
        "monthly_net_income": "14,500", "liquid_savings": 0, "employment_status": "עצמאי/ת",
        "monthly_expenses": -100, "pension_balance": "הרבה", "other_assets": True, "study_fund_balance": float("nan"),
    })
    assert accepted == {"monthly_net_income": 14500.0, "liquid_savings": 0.0, "employment_status": "עצמאי/ת"}
    assert set(rejected) == {"monthly_expenses", "pension_balance", "other_assets", "study_fund_balance"}
    assert p.monthly_expenses is None and p.pension_balance is None
    _, _, rejected = apply_profile_update(InvestorProfile(), {"employment_status": "אסטרונאוט"})
    assert "employment_status" in rejected


def test_none_records_zero_and_goal_text():
    p, accepted, rejected = apply_profile_update(InvestorProfile(), {
        "none_fields": ["monthly_debt_payments", "study_fund_balance", "investment_goal"]})
    assert rejected == {}
    assert (p.monthly_debt_payments, p.study_fund_balance, p.investment_goal) == (0.0, 0.0, "אין יעד מוגדר")
    assert accepted["monthly_debt_payments"] == 0.0
    missing = p.missing_fields()
    assert "monthly_debt_payments" not in missing and "investment_goal" not in missing


def test_unknown_is_recorded_and_not_asked_again():
    p, accepted, rejected = apply_profile_update(InvestorProfile(age=30), {"unknown_fields": ["pension_balance"]})
    assert rejected == {} and accepted == {"pension_balance": "unknown"}
    assert p.pension_balance is None and p.unknown_fields == ["pension_balance"]
    assert "pension_balance" not in p.missing_fields()
    # שוב "לא יודע" לא משכפל
    p, _, _ = apply_profile_update(p, {"unknown_fields": ["pension_balance"]})
    assert p.unknown_fields == ["pension_balance"]
    # ערך אמיתי בהמשך מחליף את "לא יודע"
    p, _, _ = apply_profile_update(p, {"pension_balance": 80000})
    assert p.pension_balance == 80000 and p.unknown_fields == []
    # וגם "אין" מחליף אותו
    p, _, _ = apply_profile_update(p.model_copy(update={"study_fund_balance": None}),
                                   {"unknown_fields": ["study_fund_balance"]})
    p, _, _ = apply_profile_update(p, {"none_fields": ["study_fund_balance"]})
    assert p.study_fund_balance == 0.0 and "study_fund_balance" not in p.unknown_fields


def test_unknown_and_none_rules():
    start = InvestorProfile(monthly_net_income=10000)
    p, accepted, rejected = apply_profile_update(start, {
        "unknown_fields": ["age", "investment_horizon_years", "monthly_net_income", "favorite_color"],
        "none_fields": ["employment_status", "monthly_deposit"],
    })
    assert accepted == {}
    assert set(rejected) == {"age", "investment_horizon_years", "monthly_net_income", "favorite_color",
                             "employment_status", "monthly_deposit"}
    assert p == start  # שדות ליבה חייבים ערך; לשדה שיש לו ערך אי אפשר לומר "לא יודע"
    _, _, rejected = apply_profile_update(InvestorProfile(), {"unknown_fields": "liquid_savings", "none_fields": 5})
    assert "none_fields" in rejected and "liquid_savings" not in rejected  # מחרוזת בודדת מתקבלת כרשימה


def test_value_together_with_unknown_or_none_is_rejected():
    p, accepted, rejected = apply_profile_update(InvestorProfile(), {
        "liquid_savings": 5000, "unknown_fields": ["liquid_savings", "other_assets"],
        "none_fields": ["other_assets", "monthly_expenses"]})
    assert set(rejected) == {"liquid_savings", "other_assets"}
    assert p.liquid_savings is None and p.other_assets is None and p.unknown_fields == []
    assert accepted == {"monthly_expenses": 0.0}


# ---------- מצב משפחתי והכנסת בן/בת זוג ----------
def test_married_without_spouse_income_is_missing():
    for status in ("נשוי", "ידוע בציבור"):
        p, accepted, rejected = apply_profile_update(InvestorProfile(age=40), {"marital_status": status})
        assert accepted == {"marital_status": status} and rejected == {}
        assert p.spouse_income_required()
        assert p.missing_fields()[0] == "spouse_monthly_net_income"
        p, _, _ = apply_profile_update(p, {"spouse_monthly_net_income": 12000})
        assert p.spouse_monthly_net_income == 12000 and "spouse_monthly_net_income" not in p.missing_fields()


def test_single_does_not_need_spouse_income():
    for status in ("רווק", "גרוש", "אלמן"):
        p, _, _ = apply_profile_update(InvestorProfile(age=40), {"marital_status": status})
        assert not p.spouse_income_required()
        assert "spouse_monthly_net_income" not in p.missing_fields()
        assert p.missing_fields()[0] == "employment_status"
    assert "spouse_monthly_net_income" not in InvestorProfile().missing_fields()  # עוד לא ידוע המצב


def test_invalid_marital_status_and_spouse_income_are_rejected():
    p, accepted, rejected = apply_profile_update(InvestorProfile(), {"marital_status": "מסובך",
                                                                     "spouse_monthly_net_income": -500})
    assert accepted == {} and set(rejected) == {"marital_status", "spouse_monthly_net_income"}
    assert "רווק" in rejected["marital_status"]  # הסיבה מפרטת את האפשרויות
    assert p.marital_status is None and p.spouse_monthly_net_income is None
    assert "marital_status" in p.missing_fields()


def test_spouse_not_working_records_zero():
    p, _, _ = apply_profile_update(InvestorProfile(marital_status="נשוי"),
                                   {"none_fields": ["spouse_monthly_net_income"]})
    assert p.spouse_monthly_net_income == 0.0 and "spouse_monthly_net_income" not in p.missing_fields()


def test_tool_spec_has_marital_fields_and_no_none_examples():
    fn = next(t for t in tool_specs() if t["function"]["name"] == "update_profile")["function"]
    props = fn["parameters"]["properties"]
    assert props["marital_status"]["enum"] == ["רווק", "נשוי", "ידוע בציבור", "גרוש", "אלמן"]
    assert "spouse_monthly_net_income" in props
    assert "spouse_monthly_net_income" in props["none_fields"]["items"]["enum"]
    texts = [fn["description"], *(str(v.get("description", "")) for v in props.values())]
    assert not any("(אין" in t or ", אין" in t for t in texts)  # בלי דוגמאות שמתחילות ב"אין ..."


def test_update_profile_spec_lists_new_fields():
    spec = next(t for t in tool_specs() if t["function"]["name"] == "update_profile")["function"]["parameters"]
    props = spec["properties"]
    for field in FINANCE:
        assert field in props
    assert "age" not in props["unknown_fields"]["items"]["enum"]
    assert "employment_status" not in props["none_fields"]["items"]["enum"]
    assert "investment_goal" in props["none_fields"]["items"]["enum"]


# ---------- הכלים עצמם ----------
def test_update_profile_tool_reports_next_field():
    result, p = run_profile_tool("update_profile", {"age": 28, "investment_horizon_years": -3}, InvestorProfile())
    assert result["accepted"] == {"age": 28}
    assert "investment_horizon_years" in result["rejected"]
    assert result["next_field"] == "marital_status" and result["complete"] is False
    assert result["missing"] == INTERVIEW_ORDER[1:]
    assert p.age == 28


def test_add_restriction_rejects_bad_input_without_changing_profile():
    p = complete_profile()
    for args in ({"item": ""}, {"item": "   "}, {"item": "x" * 61}, {"item": "ZIM", "kind": "no_sell"}, {}):
        result, same = run_profile_tool("add_restriction", args, p)
        assert "error" in result and same == p


def test_add_restriction_saves_no_buy():
    result, p = run_profile_tool("add_restriction", {"item": " zim "}, complete_profile())
    assert p.no_buy_symbols == ["ZIM"] and "לא לקנות: ZIM" in p.restrictions
    assert result["saved"] and result["no_buy_symbols"] == ["ZIM"] and "replan" not in result
    # הוספה חוזרת לא יוצרת כפילות
    _, p = run_profile_tool("add_restriction", {"item": "ZIM"}, p)
    assert p.no_buy_symbols == ["ZIM"] and p.restrictions.count("לא לקנות: ZIM") == 1


def test_add_restriction_accepts_hebrew_asset_class():
    _, p = run_profile_tool("add_restriction", {"item": 'אג"ח  קונצרני'}, InvestorProfile())
    assert p.no_buy_symbols == ['אג"ח קונצרני'] and 'לא לקנות: אג"ח קונצרני' in p.restrictions


def test_old_saved_profile_with_removed_fields_still_loads():
    p = InvestorProfile.model_validate_json('{"age": 40, "no_sell_symbols": ["ZIM"], "restrictions": ["לא למכור: ZIM"], '
                                            '"max_single_asset_weight": 0.2}')
    assert p.age == 40 and p.no_buy_symbols == [] and p.restrictions == []  # "לא למכור" ישן נמחק
    assert "max_single_asset_weight" not in p.model_dump()


def test_profile_tools_are_exposed_to_model():
    names = {t["function"]["name"] for t in tool_specs()}
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
    assert "investment_horizon_years" in result["missing"]
    # הודעת "פרופיל נוכחי" עודכנה בתוך הלולאה, והפרופיל נשמר ב-store
    assert '"age":33' in fake.calls[1]["messages"][1]["content"]
    assert s.load_profile(uid).age == 33


def test_no_buy_restriction_saved_in_chat_turn(monkeypatch):
    """המשתמש אומר "אל תקנה TSLA": ההגבלה נשמרת בפרופיל וב-store באותו תור."""
    fake = FakeClient([
        Msg(tool_calls=[Call("c1", "add_restriction", json.dumps({"item": "TSLA"}))]),
        final("רשמתי: לא לקנות TSLA"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = concentrated_store()
    reply, p = agent.chat_step([{"role": "user", "content": "אל תקנה TSLA"}], complete_profile(), s, uid)

    assert p.no_buy_symbols == ["TSLA"] and s.load_profile(uid).no_buy_symbols == ["TSLA"]
    assert tool_results(fake.calls[1])[-1]["saved"]


def test_multi_turn_interview_until_complete(monkeypatch):
    """ראיון מלא לפי הסדר הקבוע, שאלה אחת בכל תור, כולל "לא יודע" ו"אין"."""
    s, uid = concentrated_store()
    turns = [
        ("אני בן 30", {"age": 30}, "marital_status"),
        ("נשוי", {"marital_status": "נשוי"}, "spouse_monthly_net_income"),
        ("אשתי מרוויחה 11 אלף נטו", {"spouse_monthly_net_income": 11000}, "employment_status"),
        ("שכיר", {"employment_status": "שכיר/ה"}, "monthly_net_income"),
        ("14,500 נטו", {"monthly_net_income": 14500}, "monthly_expenses"),
        ("לא יודע בדיוק", {"unknown_fields": ["monthly_expenses"]}, "monthly_deposit"),
        ("2000 בחודש", {"monthly_deposit": 2000}, "liquid_savings"),
        ("30 אלף", {"liquid_savings": 30000}, "monthly_debt_payments"),
        ("אין לי חובות", {"none_fields": ["monthly_debt_payments"]}, "pension_balance"),
        ("לא יודע", {"unknown_fields": ["pension_balance"]}, "study_fund_balance"),
        ("אין לי קרן השתלמות", {"none_fields": ["study_fund_balance"]}, "other_assets"),
        ("אין", {"none_fields": ["other_assets"]}, "investment_goal"),
        ("לחסוך לדירה", {"investment_goal": "דירה"}, "investment_horizon_years"),
        ("ל-25 שנה", {"investment_horizon_years": 25, "recommended_risk_level": "אגרסיבי"}, "risk_confirmed"),
        ("מאשר את האגרסיבי", {"risk_confirmed": True}, None),
    ]
    history, profile, asked, special = [], InvestorProfile(), [], set()
    for text, args, expected_next in turns:
        fake = FakeClient([Msg(tool_calls=[Call("c", "update_profile", json.dumps(args, ensure_ascii=False))]),
                           final("שאלה הבאה")])
        monkeypatch.setattr(agent, "client", fake)
        history.append({"role": "user", "content": text})
        reply, profile = agent.chat_step(history, profile, s, uid)
        history.append({"role": "assistant", "content": reply})
        [result] = tool_results(fake.calls[1])
        assert result["next_field"] == expected_next and result["rejected"] == {}
        asked.append(result["next_field"])
        # שדה שנענה "לא יודע" או "אין" לא חוזר לרשימת החסרים בשום תור אחר כך
        special |= set(args.get("unknown_fields", [])) | set(args.get("none_fields", []))
        assert not special & set(result["missing"])

    assert len(asked) == len(set(asked))  # אף שדה לא נשאל פעמיים
    assert result["complete"] and profile.is_complete() and profile.missing_fields() == []
    assert profile.unknown_fields == ["monthly_expenses", "pension_balance"]
    assert (profile.monthly_debt_payments, profile.study_fund_balance, profile.other_assets) == (0.0, 0.0, 0.0)
    assert profile.monthly_expenses is None and profile.pension_balance is None
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
        Msg(tool_calls=[Call("c1", "update_profile", '{"age": 50}'), Call("c2", "get_proposal")]),
        final("בסדר"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = concentrated_store()
    agent.chat_step([{"role": "user", "content": "בן 50"}], InvestorProfile(), s, uid)
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[agent] round")]
    assert len(lines) == 2
    assert lines[0].startswith("[agent] round 1: LLM ") and "update_profile (" in lines[0] and "get_proposal (" in lines[0]
    assert lines[1].startswith("[agent] round 2: LLM ") and "tools: none" in lines[1]
