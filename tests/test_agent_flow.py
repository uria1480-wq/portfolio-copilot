import os

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

