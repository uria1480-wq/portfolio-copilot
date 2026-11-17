import re
import zlib

from portfolio_copilot.agent_tools import run_tool, tool_specs
from portfolio_copilot.db import Store
from portfolio_copilot.rag import KnowledgeBase, chunk_text, load_folder
from portfolio_copilot.schemas import InvestorProfile


def fake_embed(texts):
    """וקטור פשוט לפי מילים, כדי לבדוק בלי רשת ובלי מודל אמיתי."""
    vectors = []
    for t in texts:
        v = [0.0] * 256
        for w in re.findall(r"\w+", t):
            v[zlib.crc32(w.encode()) % 256] += 1.0
        vectors.append(v)
    return vectors


FEES = "דמי ניהול בחשבון מסחר הם חצי אחוז בשנה.\n\nעמלת קניה של מניה היא עשירית אחוז."
TAX = "מס רווחי הון חל על רווח ממכירת ניירות ערך.\n\nהפסדים מקוזזים מול רווחים באותה שנה."


def kb_with_docs():
    kb = KnowledgeBase(":memory:", embed=fake_embed)
    kb.add_document("fees.md", FEES)
    kb.add_document("tax.md", TAX)
    return kb


def test_chunking_respects_max_and_keeps_all_text():
    text = "\n\n".join(f"פסקה {i} " + "מילה " * 60 for i in range(6))
    chunks = chunk_text(text, max_chars=500, overlap=50)
    assert len(chunks) > 1 and all(len(c) <= 500 for c in chunks)
    assert "פסקה 5" in " ".join(chunks)


def test_search_returns_the_relevant_source_first():
    kb = kb_with_docs()
    top = kb.search("מה דמי הניהול בחשבון מסחר", k=2)[0]
    assert top["source"] == "fees.md"
    assert kb.search("איך מקזזים הפסדים ממס רווחי הון", k=1)[0]["source"] == "tax.md"


def test_reingest_unchanged_is_skipped_and_changed_is_replaced():
    kb = kb_with_docs()
    assert kb.add_document("fees.md", FEES) == 0
    assert kb.add_document("fees.md", FEES + "\n\nעמלת העברה היא עשרה שקלים.") > 0
    assert kb.sources() == ["fees.md", "tax.md"]
    assert any("עמלת העברה" in h["text"] for h in kb.search("עמלת העברה", k=3))


def test_empty_kb_returns_nothing():
    assert KnowledgeBase(":memory:", embed=fake_embed).search("כלום") == []


def test_load_folder_reads_txt_and_md(tmp_path):
    (tmp_path / "a.md").write_text(FEES, encoding="utf-8")
    (tmp_path / "b.txt").write_text(TAX, encoding="utf-8")
    (tmp_path / "ignore.pdf").write_text("x")
    kb = KnowledgeBase(":memory:", embed=fake_embed)
    added = load_folder(kb, tmp_path)
    assert set(added) == {"a.md", "b.txt"} and kb.sources() == ["a.md", "b.txt"]
    assert load_folder(kb, tmp_path / "missing") == {}


def test_search_documents_tool_and_specs():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    kb = kb_with_docs()
    r = run_tool("search_documents", {"query": "דמי ניהול"}, s, uid, InvestorProfile(), kb=kb)
    assert r["passages"][0]["source"] == "fees.md"
    assert "error" in run_tool("search_documents", {"query": " "}, s, uid, InvestorProfile(), kb=kb)
    assert "error" in run_tool("search_documents", {"query": "x"}, s, uid, InvestorProfile(), kb=None)
    names = lambda specs: {t["function"]["name"] for t in specs}
    assert "search_documents" in names(tool_specs(True)) and "search_documents" not in names(tool_specs(False))