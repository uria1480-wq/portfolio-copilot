import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from types import SimpleNamespace

from portfolio_copilot import agent
from portfolio_copilot.agent_tools import tool_specs
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile

names = lambda specs: {t["function"]["name"] for t in specs}


def test_agent_sees_only_profile_proposal_and_monthly_tools():
    assert names(tool_specs()) == {"update_profile", "add_restriction", "remove_restriction", "get_proposal", "get_monthly_allocation"}


def test_chat_step_offers_the_tools(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        msg = SimpleNamespace(content="בסדר", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(agent, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    s = Store(":memory:")
    agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(), s, s.get_or_create_user("demo"))
    assert names(calls[0]["tools"]) == names(tool_specs())


def test_system_prompt_matches_current_app():
    prompt = agent.SYSTEM_PROMPT
    for gone in ("get_portfolio", "plan_deposit", "get_documents", "search_documents", "propose_plan",
                 "salary_received", "החזקות", "לא מוכר", "allow_sell"):
        assert gone not in prompt
    for screen in ("היכרות", "המצב שלי", "ניהול חודשי", "שאל את הסוכן", "get_proposal", "get_monthly_allocation"):
        assert screen in prompt


def test_system_prompt_covers_failures_found_in_evals():
    """הכללים שנוספו אחרי סט ההערכה (evals/README.md): מכירה, מחוץ לתחום, אחוז מהנטו, "למה", תשובה לא ברורה."""
    prompt = agent.SYSTEM_PROMPT
    assert "בקשה למכור" in prompt and "אל תקרא ל-add_restriction" in prompt
    assert "מחוץ לתחום" in prompt and "אל תציע הקצאה" in prompt
    assert "אל תחשב את האחוז בעצמך" in prompt and "ניהול חודשי" in prompt
    assert 'חובה לקרוא לו גם לשאלות "למה"' in prompt
    assert "תשובה לא ברורה" in prompt and "שאל שוב" in prompt

