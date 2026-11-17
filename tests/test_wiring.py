import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

import json
from types import SimpleNamespace

from portfolio_copilot import agent
from portfolio_copilot.agent_tools import run_tool, tool_specs
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile

names = lambda specs: {t["function"]["name"] for t in specs}


def test_all_tools_coexist():
    base = {"update_profile", "add_restriction",
            "get_portfolio", "plan_deposit", "get_documents", "propose_plan", "salary_received"}
    assert names(tool_specs(False)) == base
    assert names(tool_specs(True)) == base | {"search_documents"}


def test_get_documents_returns_latest_payslips_and_average():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    assert run_tool("get_documents", {}, s, uid, InvestorProfile())["payslips"] == []
    for period, net in [("2026-09", 9000.0), ("2026-10", 9500.0)]:
        s.save_document(uid, {"doc_type": "payslip", "period": period, "data": {},
                              "summary": {"period": period, "net_to_bank": net}, "warnings": []})
    r = run_tool("get_documents", {}, s, uid, InvestorProfile())
    assert r["payslips"][0]["period"] == "2026-10" and r["avg_net_to_bank"] == 9250.0


def test_chat_step_passes_kb_so_search_tool_is_offered(monkeypatch):
    calls = []
    final = json.dumps({"reply": "בסדר", "profile": {}}, ensure_ascii=False)

    def create(**kwargs):
        calls.append(kwargs)
        msg = SimpleNamespace(content=final, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(agent, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(), s, uid, kb=object())
    agent.chat_step([{"role": "user", "content": "היי"}], InvestorProfile(), s, uid)
    assert "search_documents" in names(calls[0]["tools"]) and "search_documents" not in names(calls[1]["tools"])


def test_get_documents_includes_fund_reports():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    s.save_document(uid, {"doc_type": "fund_report", "period": "2026-Q1", "data": {},
                          "summary": {"fund_name": "קופה", "balance_end": 1000.0, "fee_on_savings_pct": 0.4}, "warnings": []})
    r = run_tool("get_documents", {}, s, uid, InvestorProfile())
    assert r["payslips"] == [] and r["fund_reports"][0]["fee_on_savings_pct"] == 0.4