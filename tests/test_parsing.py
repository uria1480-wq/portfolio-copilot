import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from types import SimpleNamespace

from portfolio_copilot import agent
from portfolio_copilot.schemas import InvestorProfile


def counting_client(*contents):
    """לקוח מדומה שמחזיר את התשובות לפי הסדר וסופר קריאות."""
    items, calls = list(contents), []

    def create(**kwargs):
        calls.append(kwargs)
        content = items.pop(0) if len(items) > 1 else items[0]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), calls


def fake_client(content):
    return counting_client(content)[0]


def test_raw_newline_inside_json_string_is_accepted():
    data = agent.extract_json('```json\n{"reply": "שורה ראשונה\nשורה שנייה", "profile": {"age": 30}}\n```')
    assert data["profile"]["age"] == 30 and "שורה שנייה" in data["reply"]


def test_plain_text_reply_is_returned_as_is(monkeypatch):
    monkeypatch.setattr(agent, "client", fake_client("  כדאי להתחיל מקרן חירום.\nמה הגיל שלך?  "))
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(age=5))
    assert reply == "כדאי להתחיל מקרן חירום.\nמה הגיל שלך?" and profile.age == 5


def test_json_reply_is_extracted_and_profile_field_is_ignored(monkeypatch):
    monkeypatch.setattr(agent, "client", fake_client('{"reply": "היי\nמה שלומך?", "profile": {"age": 41}}'))
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile())
    assert reply == "היי\nמה שלומך?" and profile.age is None


def test_json_in_code_fence_is_extracted(monkeypatch):
    monkeypatch.setattr(agent, "client", fake_client('```json\n{"reply": "שלום"}\n```'))
    reply, _ = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile())
    assert reply == "שלום"


def test_broken_json_still_shows_the_reply_text(monkeypatch):
    broken = '{"reply": "כדאי להתחיל \\"בקטן\\"", "profile": {"age": 30,, }'
    monkeypatch.setattr(agent, "client", fake_client(broken))
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(age=5))
    assert reply == 'כדאי להתחיל "בקטן"' and profile.age == 5


def test_repair_call_is_never_made(monkeypatch):
    client, calls = counting_client("טקסט חופשי בלי JSON", '{"reply": "תיקון", "profile": {"age": 30}}')
    monkeypatch.setattr(agent, "client", client)
    reply, profile = agent.chat_step([{"role": "user", "content": "אני בן 30"}], InvestorProfile())
    assert reply == "טקסט חופשי בלי JSON" and profile.age is None
    assert len(calls) == 1


def test_broken_json_object_without_reply_gets_generic_message(monkeypatch, capsys):
    monkeypatch.setattr(agent, "client", fake_client('{"profile": {"age": 30,, }'))
    reply, profile = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile())
    assert reply == agent.FALLBACK_REPLY and profile.age is None
    assert "בלי reply" in capsys.readouterr().out


def test_empty_reply_gets_generic_message(monkeypatch):
    monkeypatch.setattr(agent, "client", fake_client(None))
    reply, _ = agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile())
    assert reply == agent.FALLBACK_REPLY


def test_agent_and_payslip_share_one_json_parser():
    from portfolio_copilot import documents

    assert agent.extract_json is documents.extract_json and not hasattr(documents, "_parse_json")
    assert documents.extract_json('לפני {"a": "שורה\nשנייה"} אחרי') == {"a": "שורה\nשנייה"}


def test_empty_model_content_is_a_json_error_not_a_crash():
    import json

    import pytest
    from portfolio_copilot import documents

    with pytest.raises(json.JSONDecodeError):
        documents.extract_json(None)

