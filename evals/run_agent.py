"""מריץ את סט ההערכה לסוכן מול Gemini אמיתי (צורך מכסה: בערך 2-3 קריאות ל-LLM למקרה בכל חזרה).

הרצה:  uv run python evals/run_agent.py [--repeat N] [--delay שניות] [--only טקסט]
בנוסף לבחירת הכלי, בודק שאין מספרים מומצאים: כל מספר בתשובה חייב להופיע בפלט כלי, בהודעת המשתמש או בפרופיל.
"""
import argparse
import json
import sys
import time
from datetime import date

from agent_cases import CASES, PROFILE
from common import numbers_in, pct, print_table, utf8_console
from live import model_name, run_turn

from portfolio_copilot.schemas import InvestorProfile


def allowed_numbers(case, profile: InvestorProfile, turn, today: date) -> set[float]:
    """מאיפה מותר למספר להגיע: פלט הכלים, ההודעות של המשתמש, הפרופיל (מה שהמשתמש מסר) והתאריך."""
    sources = [json.dumps(c.result, ensure_ascii=False) for c in turn.calls]
    sources += [case.message, *(m["content"] for m in case.history if m["role"] == "user")]
    sources.append(profile.model_dump_json())
    allowed = set().union(*(numbers_in(s) for s in sources))
    return allowed | {float(today.year), float(today.month), float(today.day)}


def judge(case, profile: InvestorProfile, turn, today: date) -> tuple[bool, str]:
    if turn.error:
        return False, turn.error[:80]
    called = turn.tool_names
    problems = []
    if case.no_tools and called:
        problems.append("קרא לכלי")
    if case.tools and not any(t in called for t in case.tools):
        problems.append(f"לא קרא ל-{'/'.join(case.tools)}")
    problems += [f"קרא ל-{t} (אסור)" for t in case.forbid if t in called]
    for tool, expected in case.args.items():
        got = [c.args for c in turn.calls if c.name == tool]
        if not any(all(_same(a.get(k), v) for k, v in expected.items()) for a in got):
            problems.append(f"ארגומנטים של {tool}: {got}")
    for tool, expected in case.result.items():
        got = [c.result for c in turn.calls if c.name == tool]
        if not any(all(_same(r.get(k), v) for k, v in expected.items()) for r in got):
            problems.append(f"תוצאה של {tool}: {[{k: r.get(k) for k in expected} for r in got]}")
    if case.reply_any and not any(p in turn.reply for p in case.reply_any):
        problems.append("התשובה לא מסבירה כמצופה")
    invented = sorted(numbers_in(turn.reply) - allowed_numbers(case, profile, turn, today))
    if invented:
        problems.append(f"מספרים מומצאים: {', '.join(f'{n:g}' for n in invented)}")
    actual = f"כלים: {','.join(called) or 'בלי כלי'}"
    if problems:
        actual += " | " + "; ".join(problems)
    return not problems, actual


def _same(a, b) -> bool:
    if isinstance(b, (int, float)) and not isinstance(b, bool):
        try:
            return abs(float(a) - b) < 0.01
        except (TypeError, ValueError):
            return False
    return a == b


def show_expected(case) -> str:
    parts = ["בלי כלי" if case.no_tools else "/".join(case.tools) if case.tools else "כל כלי"]
    if case.forbid:
        parts.append("לא " + "/".join(case.forbid))
    parts += [f"{t}({a})" for t, a in case.args.items()]
    parts += [f"{t}→{r}" for t, r in case.result.items()]
    if case.reply_any:
        parts.append(f"בתשובה: {case.reply_any[0]}…")
    return ", ".join(parts)


def main(argv=None) -> int:
    utf8_console()
    parser = argparse.ArgumentParser(description="סט הערכה לסוכן (Gemini אמיתי)")
    parser.add_argument("--repeat", type=int, default=1, help="כמה פעמים להריץ כל מקרה")
    parser.add_argument("--delay", type=float, default=4.0, help="השהיה בשניות בין מקרים (מגבלת קצב לדקה)")
    parser.add_argument("--only", default="", help="רק מקרים ששמם מכיל את הטקסט")
    parser.add_argument("--show-replies", action="store_true", help="להדפיס את תשובת הסוכן בכל מקרה")
    args = parser.parse_args(argv)

    today = date.today()
    selected = [c for c in CASES if args.only in c.name]
    print(f"סט הערכה לסוכן: {len(selected)} מקרים × {args.repeat} | מודל: {model_name()} | היום: {today}\n")
    rows, total_ok, total_runs, full_pass, llm_calls, errors = [], 0, 0, 0, 0, 0
    for case in selected:
        profile = InvestorProfile(**{**PROFILE, **case.profile})
        history = [*case.history, {"role": "user", "content": case.message}]
        ok_count, runs, last = 0, 0, ""
        for _ in range(args.repeat):
            turn = run_turn(history, profile, today)
            llm_calls += turn.llm_calls
            ok, last = judge(case, profile, turn, today)
            if turn.error:
                errors += 1
            else:
                runs += 1
                ok_count += ok
            if args.show_replies:
                print(f"--- {case.name}: {turn.reply}\n")
            if args.delay:
                time.sleep(args.delay)
        total_ok += ok_count
        total_runs += runs
        full_pass += runs > 0 and ok_count == runs
        status = "שגיאה" if runs == 0 else "עבר" if ok_count == runs else "נכשל"
        rows.append([case.name, f'"{case.message}" → {show_expected(case)}', last, f"{status} {ok_count}/{runs}"])
    print_table(["מקרה", "מצופה", "בפועל (ריצה אחרונה)", "תוצאה"], rows, max_width=85)
    print(f"\nסיכום: {full_pass}/{len(selected)} מקרים עברו בכל הריצות. "
          f"ריצות שעברו: {total_ok}/{total_runs} ({pct(total_ok, total_runs)}), בלי ריצות שנפלו בתקשורת. "
          f"קריאות ל-LLM: {llm_calls}. שגיאות תקשורת: {errors}.")
    return 0 if full_pass == len(selected) and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
