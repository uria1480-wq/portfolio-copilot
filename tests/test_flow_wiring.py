"""הפעלה וחיווט: --fresh, --share וסיסמה, בניית הממשק, גבול ה-client, קונסולה ונקודת הכניסה."""
import os

import pytest

pytest.importorskip("gradio")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://localhost")

from types import SimpleNamespace

from test_flow_interview import complete_profile, new_store

from portfolio_copilot import agent
from portfolio_copilot import app as appmod
from portfolio_copilot.db import Store
from portfolio_copilot.schemas import InvestorProfile


def test_fresh_flag_uses_memory_store_and_default_uses_file(monkeypatch):
    """בודק את שני המצבים בלי לפתוח את הקובץ האמיתי ובלי להפעיל את השרת."""
    paths, launched = [], []

    def fake_store(path="data/portfolio.db"):
        paths.append(path)
        return Store(":memory:")  # לא נוגעים ב-data/portfolio.db אמיתי

    fake_demo = SimpleNamespace(launch=lambda **kw: launched.append(kw))
    monkeypatch.setattr(appmod, "Store", fake_store)
    monkeypatch.setattr(appmod, "build_demo", lambda store, uid: (fake_demo, {}))

    appmod.main(["--fresh"])
    appmod.main([])
    assert paths == [":memory:", "data/portfolio.db"] and len(launched) == 2
    assert appmod.parse_args(["--fresh"]).fresh and not appmod.parse_args([]).fresh
    assert all(kw["share"] is False and "auth" not in kw for kw in launched)  # ברירת מחדל: מקומי בלבד


def fake_launch(monkeypatch):
    launched = []
    monkeypatch.setattr(appmod, "Store", lambda path="data/portfolio.db": Store(":memory:"))
    monkeypatch.setattr(appmod, "build_demo",
                        lambda store, uid: (SimpleNamespace(launch=lambda **kw: launched.append(kw)), {}))
    return launched


def test_share_flag_reads_password_and_username_from_env(monkeypatch):
    launched = fake_launch(monkeypatch)
    monkeypatch.setenv("SHARE_PASSWORD", "from-env-secret")
    monkeypatch.setenv("SHARE_USERNAME", "team")
    appmod.main(["--fresh", "--share"])
    assert launched == [{"share": True, "auth": ("team", "from-env-secret")}]


def test_share_without_username_uses_default(monkeypatch):
    monkeypatch.delenv("SHARE_USERNAME", raising=False)
    assert appmod.share_settings(True, {"SHARE_PASSWORD": "x"}) == {"share": True, "auth": ("family", "x")}
    assert appmod.share_settings(False, {"SHARE_PASSWORD": "x"}) == {"share": False}


@pytest.mark.parametrize("password", [None, "", "   "])
def test_share_without_password_refuses_to_start(monkeypatch, password):
    launched = fake_launch(monkeypatch)
    if password is None:
        monkeypatch.delenv("SHARE_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("SHARE_PASSWORD", password)
    with pytest.raises(SystemExit) as e:
        appmod.main(["--fresh", "--share"])
    assert "SHARE_PASSWORD" in str(e.value) and launched == []


def test_no_password_is_written_in_app_code():
    source = open(appmod.__file__, encoding="utf-8").read()
    assert "u12345" not in source and "share=True" not in source


def test_fresh_store_starts_clean_every_time():
    first = appmod.open_store(fresh=True)
    uid = first.get_or_create_user("demo")
    first.save_profile(uid, complete_profile())
    second = appmod.open_store(fresh=True)
    assert second.load_profile(second.get_or_create_user("demo")) == InvestorProfile()


def test_demo_builds_with_chat_intake():
    store, uid = new_store()
    demo, _ = appmod.build_demo(store, uid)
    labels = {getattr(b, "label", None) for b in demo.blocks.values()}
    assert "שיחת היכרות" in labels and "גיל" not in labels  # טופס השאלון כבר לא בשלב 1


def test_three_stages_and_no_analysis_tab():
    from portfolio_copilot.ui import STAGES, stages_html
    assert [k for k, _ in STAGES] == ["intake", "picture", "monthly"]
    assert "ניתוח והדרכה" not in stages_html({})
    store, uid = new_store()
    demo, _ = appmod.build_demo(store, uid)
    texts = {str(getattr(b, attr, "")) for b in demo.blocks.values() for attr in ("label", "value")}
    assert "המשך לניהול חודשי" in texts and "3. ניהול חודשי" in texts
    assert "יש לי שאלה? דבר עם הסוכן" in texts
    assert not any("ניתוח והדרכה" in t or "נתח את המצב" in t for t in texts)


def test_app_does_not_see_llm_client_or_model_name():
    """קריאות ל-LLM מוסתרות מאחורי ממשק בשמות של התחום (CLAUDE.md)."""
    assert not hasattr(appmod, "client") and not hasattr(appmod, "MODEL_NAME")
    assert not hasattr(appmod, "read_document")


def test_read_payslip_passes_agent_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(agent, "read_document", lambda path, client, model: seen.update(
        path=path, client=client, model=model) or {"ok": True})
    assert agent.read_payslip("slip.pdf") == {"ok": True}
    assert seen == {"path": "slip.pdf", "client": agent.client, "model": agent.MODEL_NAME}


def test_utf8_console_lets_hebrew_print_on_cp1252_stream():
    import io

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    appmod.utf8_console(stream)
    print("[app] --fresh: מסד נתונים בזיכרון", file=stream)
    stream.flush()
    assert "מסד נתונים".encode("utf-8") in raw.getvalue()
    appmod.utf8_console(object())  # זרם בלי reconfigure לא נשבר


def test_console_script_points_to_app_main():
    import tomllib
    from importlib import import_module
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    module, func = pyproject["project"]["scripts"]["portfolio-copilot"].split(":")
    assert getattr(import_module(module), func) is appmod.main


def test_gemini_smoke_script_is_not_collected_by_pytest():
    from pathlib import Path

    root = Path(__file__).parents[1]
    assert not (root / "test_gemini.py").exists()
    assert not list((root / "scripts").glob("test_*.py"))


def test_evals_are_not_collected_by_pytest():
    """סטי ההערכה רצים רק בהפעלה מפורשת (חלקם קוראים ל-Gemini אמיתי)."""
    from pathlib import Path

    evals = Path(__file__).parents[1] / "evals"
    assert evals.is_dir() and not list(evals.glob("test_*.py")) and not list(evals.glob("*_test.py"))
