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


FINAL = "התיק שלך מאוזן"


def store_with_holding():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    s.upsert_holding(uid, "VT", 10)
    return s, uid


def test_tool_round_trip(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c1", "get_portfolio")]), Msg(content=FINAL)])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    reply, profile = agent.chat_step([{"role": "user", "content": "מה מצב התיק?"}], InvestorProfile(), s, uid, fetch=lambda x: 100.0)
    assert reply == "התיק שלך מאוזן" and profile == InvestorProfile()
    assert "tools" in fake.calls[0]
    tool_msg = [m for m in fake.calls[1]["messages"] if m["role"] == "tool"][0]
    assert tool_msg["tool_call_id"] == "c1" and "VT" in tool_msg["content"]


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


def test_endless_tool_calls_terminate(monkeypatch):
    fake = FakeClient([Msg(tool_calls=[Call("c", "get_portfolio")])])
    monkeypatch.setattr(agent, "client", fake)
    s, uid = store_with_holding()
    reply, _ = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(), s, uid, fetch=lambda x: 1.0)
    assert len(fake.calls) == agent.MAX_TOOL_ROUNDS + 1
    assert "tools" not in fake.calls[-1] and isinstance(reply, str)