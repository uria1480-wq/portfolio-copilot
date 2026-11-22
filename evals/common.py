"""עזרים משותפים לסטי ההערכה: קונסולה ב-UTF-8, טבלה, אחוזים, ומספרים מתוך טקסט.

סטי ההערכה לא רצים ב-pytest. מריצים אותם במפורש, למשל: uv run python evals/run_proposal.py
"""
import re
import sys


def utf8_console() -> None:
    """הדפסה בעברית גם כשהפלט מנותב לקובץ ב-Windows (cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def print_table(headers: list[str], rows: list[list[str]], max_width: int = 70) -> None:
    """טבלה פשוטה בטקסט. תא ארוך נחתך ל-max_width תווים."""
    def cut(text) -> str:
        text = " ".join(str(text).split())
        return text if len(text) <= max_width else text[: max_width - 1] + "…"

    rows = [[cut(c) for c in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = lambda cells: " | ".join(c.ljust(w) for c, w in zip(cells, widths))
    print(line(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(line(row))


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# מספור של רשימה או של כותרת בתחילת שורה: "1. ", "### 2. ", "### 🛡️ 3. ", "**4.** "
LIST_MARKER = re.compile(r"^[\s#*>-]*(?:[^\w\s#*]+\s*)?\d+[.)]\**\s", re.M)


def numbers_in(text: str) -> set[float]:
    """כל המספרים בטקסט, מנורמלים (12,500 -> 12500.0). מספור רשימה בתחילת שורה ("1. ") לא נספר."""
    text = LIST_MARKER.sub(" ", text or "")
    out = set()
    for raw in NUMBER.findall(text):
        try:
            out.add(round(float(raw.replace(",", "")), 2))
        except ValueError:
            continue
    return out


def pct(passed: int, total: int) -> str:
    return f"{100 * passed / total:.0f}%" if total else "—"
