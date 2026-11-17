import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from types import SimpleNamespace

from portfolio_copilot import agent
from portfolio_copilot.schemas import InvestorProfile


def fake_client(content):
    msg = SimpleNamespace(content=content, tool_calls=None)
    create = lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_raw_newline_inside_json_string_is_accepted():
    data = agent.extract_json('```json\n{"reply": "שורה ראשונה\nשורה שנייה", "profile": {"age": 30}}\n```')
    assert data["profile"]["age"] == 30 and "שורה שנייה" in data["reply"]


def test_chat_step_survives_model_json_with_raw_newlines(monkeypatch):
    monkeypatch.setattr(agent, "client", fake_client('{"reply": "היי\nמה שלומך?", "profile": {"age": 41}}'))
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile())
    assert "מה שלומך" in reply and profile.age == 41


def test_broken_json_still_shows_the_reply_text(monkeypatch, capsys):
    broken = '{"reply": "כדאי להתחיל מקרן חירום", "profile": {"age": 30,, }'
    monkeypatch.setattr(agent, "client", fake_client(broken))
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(age=5))
    assert reply == "כדאי להתחיל מקרן חירום" and profile.age == 5
    assert "לא ניתן לפענח" in capsys.readouterr().out


def sequence_client(*contents):
    items = list(contents)

    def create(**kwargs):
        content = items.pop(0) if len(items) > 1 else items[0]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_plain_text_is_shown_when_repair_also_fails(monkeypatch):
    monkeypatch.setattr(agent, "client", fake_client("סתם טקסט בלי JSON"))
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(age=5))
    assert reply == "סתם טקסט בלי JSON" and profile.age == 5


def test_repair_call_recovers_reply_and_profile(monkeypatch):
    fixed = '{"reply": "כדאי להתחיל בקרן חירום", "profile": {"age": 30}}'
    monkeypatch.setattr(agent, "client", sequence_client("כדאי להתחיל בקרן חירום", fixed))
    reply, profile = agent.chat_step([{"role": "user", "content": "אני בן 30"}], InvestorProfile())
    assert reply == "כדאי להתחיל בקרן חירום" and profile.age == 30


def test_broken_json_object_without_reply_gets_generic_message(monkeypatch):
    monkeypatch.setattr(agent, "client", fake_client('{"profile": {"age": 30,, }'))
    reply, _ = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile())
    assert "לנסח" in reply