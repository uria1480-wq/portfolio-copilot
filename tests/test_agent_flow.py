import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from types import SimpleNamespace

from portfolio_copilot import agent
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile


class Call:
    def __init__(self, id, name, arguments="{}"):
        self.id = id
        self.function = SimpleNamespace(name=name, arguments=arguments)


class Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant"}
        if self.content:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [{"id": c.id, "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments}}
                               for c in self.tool_calls]
        return d


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return SimpleNamespace(choices=[SimpleNamespace(message=reply)])


FINAL = "זו ההצעה שלך"


def store_with_holding():
    s = Store(":memory:")
    return s, s.get_or_create_user("demo")


def test_tool_round_trip(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c1", "get_proposal")]), Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    reply, profile = agent.chat_step([{"role": "user", "content": "מה ההצעה שלי?"}], InvestorProfile(), s, uid)
    assert reply == FINAL and profile == InvestorProfile()
    assert "tools" in fake.calls[0]
    tool_msg = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"][0]
    assert tool_msg["tool_call_id"] == "c1" and '"missing"' in tool_msg["content"]


def test_no_store_means_no_tools(monkeypatch):
    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile())
    assert "tools" not in fake.calls[0]


def test_bad_json_keeps_profile(monkeypatch):
    monkeypatch.setattr(agent, "client", FakeClient([Msg(content="לא JSON")]))
    p = InvestorProfile(age=30)
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], p)
    assert profile == p and reply == "לא JSON"


def test_system_message_includes_today(monkeypatch):
    import datetime

    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    agent.chat_step([{"role": "user", "content": "אני רוצה דירה ב-2040"}], InvestorProfile(), s, uid,
                    today=datetime.date(2031, 2, 3))
    system = [m["content"] for m in fake.calls[0]["messages"] if m["role"] == "system"]
    assert any("התאריך היום: 2031-02-03" in content for content in system)


def test_target_year_horizon_uses_injected_date(monkeypatch):
    import datetime
    import json

    fake = FakeClient([Msg(tool_calls=[Call("c1", "update_profile", json.dumps({"target_year": 2029}))]),
                       Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    _, profile = agent.chat_step([{"role": "user", "content": "דירה ב-2029"}], InvestorProfile(), s, uid,
                                 today=datetime.date(2026, 11, 19))
    assert profile.investment_horizon_years == 3


def test_endless_tool_calls_terminate(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c", "get_proposal")])])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    reply, _ = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(), s, uid)
    assert len(fake.calls) == agent.MAX_TOOL_ROUNDS + 1
    assert "tools" not in fake.calls[-1] and isinstance(reply, str)


def test_only_last_n_history_messages_are_sent(monkeypatch):
    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"הודעה {i}"} for i in range(50)]
    agent.chat_step(history, InvestorProfile(age=30))
    sent = fake.calls[0]["messages"]
    assert agent.MAX_HISTORY_MESSAGES == 20
    assert sent[2:] == history[-20:] and len(sent) == 2 + 20
    assert '"age":30' in sent[1]["content"]  # הפרופיל נשלח תמיד, גם כשההיסטוריה נחתכת
    assert len(history) == 50  # ההיסטוריה של המסך לא משתנה


def test_short_history_is_sent_whole():
    history = [{"role": "user", "content": "היי"}]
    assert agent.recent_history(history) == history and agent.recent_history(history, 0) == []


def test_every_model_call_has_a_token_cap(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c1", "get_proposal")]), Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    agent.chat_step([{"role": "user", "content": "מה ההצעה?"}], InvestorProfile(), s, uid)
    assert len(fake.calls) == 2 and all(c["max_tokens"] == agent.MAX_REPLY_TOKENS for c in fake.calls)


def test_system_prompt_names_the_course():
    assert 'פיתוח פתרונות מבוססי AI' in agent.SYSTEM_PROMPT and "מבוא לבינה מלאכותית" not in agent.SYSTEM_PROMPT


# ---------- הגנה מטענת ביצוע כוזבת ----------
@pytest.mark.parametrize("reply", ["רשמתי לפניי שאתה לא רוצה מניות.", "שמרתי את ההגבלה.", "עדכנתי את הפרופיל שלך."])
def test_save_claim_without_profile_tool_gets_a_note(monkeypatch, reply):
    fake = FakeClient([Msg(content=reply)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    out, profile = agent.chat_step([{"role": "user", "content": "אני לא רוצה מניות"}], InvestorProfile(), s, uid)
    assert out.startswith(reply) and out.endswith(f"({agent.NOT_SAVED_NOTE})") and profile == InvestorProfile()


def test_save_claim_after_profile_tool_is_left_alone(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c1", "update_profile", '{"age": 40}')]), Msg(content="עדכנתי את הגיל.")])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    out, profile = agent.chat_step([{"role": "user", "content": "אני בן 40"}], InvestorProfile(), s, uid)
    assert out == "עדכנתי את הגיל." and profile.age == 40


def test_save_claim_after_other_tool_only_still_gets_a_note(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c1", "get_proposal")]), Msg(content="רשמתי ושמרתי את ההגבלה.")])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    out, _ = agent.chat_step([{"role": "user", "content": "אל תקנה מניות"}], InvestorProfile(), s, uid)
    assert agent.NOT_SAVED_NOTE in out


def test_reply_without_save_claim_is_unchanged():
    assert agent.guard_save_claim("ההצעה שלך מוכנה.", False) == "ההצעה שלך מוכנה."
    assert agent.guard_save_claim("", False) == ""


# ---------- "למה" על ההצעה: הקוד מכריח get_proposal ----------
def complete():
    return InvestorProfile(age=35, marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=20000,
                           monthly_expenses=10000, liquid_savings=60000, monthly_debt_payments=0,
                           monthly_deposit=3000, pension_balance=1, study_fund_balance=1, other_assets=0,
                           investment_goal="פרישה", investment_horizon_years=20, recommended_risk_level="מאוזן",
                           risk_confirmed=True)


@pytest.mark.parametrize("question", ['למה יש לי אג"ח בתמהיל?', "מדוע 65% מניות?", "למה הכספית כל כך גבוהה?",
                                      "מה הסיבה למסלול הפנסיה הזה?"])
def test_why_question_about_proposal_forces_get_proposal_in_first_round_only(monkeypatch, question):
    fake = FakeClient([Msg(tool_calls=[Call("c1", "get_proposal")]), Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    agent.chat_step([{"role": "user", "content": question}], complete(), s, uid)
    assert fake.calls[0]["tool_choice"] == agent.FORCE_PROPOSAL and "tool_choice" not in fake.calls[1]


@pytest.mark.parametrize("question", ["מה ההצעה שלי?", "למה אתה שואל את זה?", "תודה!"])
def test_other_messages_do_not_force_a_tool(monkeypatch, question):
    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    agent.chat_step([{"role": "user", "content": question}], complete(), s, uid)
    assert "tool_choice" not in fake.calls[0]


def test_why_question_during_interview_does_not_force(monkeypatch):
    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    agent.chat_step([{"role": "user", "content": "למה אתה שואל על הפנסיה שלי?"}], InvestorProfile(age=30), s, uid)
    assert "tool_choice" not in fake.calls[0]


def test_without_store_there_is_no_forcing(monkeypatch):
    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    agent.chat_step([{"role": "user", "content": 'למה יש לי אג"ח בתמהיל?'}], complete())
    assert "tool_choice" not in fake.calls[0] and "tools" not in fake.calls[0]


# ---------- תשובה קבועה בקוד: מחוץ לתחום ומכירה ----------
OUT_OF_SCOPE_MESSAGES = ["מה דעתך על ביטקוין?", "כמה לשים בקריפטו?", "כדאי לקנות Bitcoin?", "מה עם BTC?",
                         'כדאי לי להשקיע בנדל"ן?', "כדאי לקנות זהב?", "מה דעתך על מטבעות דיגיטליים?",
                         "אתריום זה רעיון טוב?"]
SELL_FIXED_MESSAGES = ["תמכור את המניות שלי", "מכור את הכספית", "אני רוצה למכור את האג\"ח", "ולמכור הכל?",
                       "תמכרי לי את המדד"]
PASS_THROUGH_MESSAGES = ["מה דעתך על ההצעה?", "מה ההצעה שלי?", "אל תקנה לי מניות", "אני לא רוצה לקנות מניות",
                         "אני מוכר בחנות", "יש לי נדל\"ן בשווי 2 מיליון", "למה כתוב ריכוז בנדל\"ן?",
                         "אני רוצה למכור? לא, פשוט לא לקנות יותר מניות", "כמה חסר לי בקרן החירום?"]


@pytest.mark.parametrize("message", OUT_OF_SCOPE_MESSAGES + SELL_FIXED_MESSAGES)
def test_fixed_reply_without_llm(monkeypatch, message):
    fake = FakeClient([Msg(content="לא אמור להיקרא")])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    reply, profile = agent.chat_step([{"role": "user", "content": message}], complete(), s, uid)
    assert reply == agent.OUT_OF_SCOPE_REPLY and fake.calls == [] and profile == complete()


@pytest.mark.parametrize("message", PASS_THROUGH_MESSAGES)
def test_regular_messages_go_to_the_model(monkeypatch, message):
    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    reply, _ = agent.chat_step([{"role": "user", "content": message}], complete(), s, uid)
    assert reply == FINAL and len(fake.calls) == 1


def test_out_of_scope_word_during_interview_goes_to_the_model(monkeypatch):
    """בראיון "נדל"ן" הוא תשובה על נכסים אחרים, ולא בקשה להקצאה."""
    fake = FakeClient([Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    reply, _ = agent.chat_step([{"role": "user", "content": 'נדל"ן, בערך מיליון'}], InvestorProfile(age=30))
    assert reply == FINAL
    assert agent.fixed_reply_for("תמכור הכל", InvestorProfile()) == agent.OUT_OF_SCOPE_REPLY  # מכירה: גם בראיון


def test_fixed_reply_text_and_word_lists():
    assert agent.OUT_OF_SCOPE_REPLY == ("אין בפרויקט המלצות מכירה או הקצאה לנכסים מחוץ לחמשת סוגי הנכסים. "
                                        "אפשר לראות את ההצעה או לשנות הגבלת קנייה.")
    assert "ביטקוין" in agent.OUT_OF_SCOPE_WORDS and 'נדל"ן' in agent.OUT_OF_SCOPE_WORDS
    assert agent.fixed_reply_for("", complete()) is None and agent.fixed_reply_for(None, complete()) is None

