"""מריץ את סט ההערכה לראיון מול Gemini אמיתי (צורך מכסה: בערך 2-3 קריאות ל-LLM למקרה בכל חזרה).

הרצה:  uv run python evals/run_interview.py [--repeat N] [--delay שניות] [--only טקסט]
המודל לא דטרמיניסטי, ולכן --repeat מריץ כל מקרה N פעמים ומדפיס אחוז הצלחה לכל מקרה.
"""
import argparse
import sys
import time
from datetime import date

from common import pct, print_table, utf8_console
from interview_cases import FULL, UNCHANGED, UNKNOWN, cases
from live import model_name, run_turn

from portfolio_copilot.schemas import InvestorProfile


def start_profile(case) -> InvestorProfile:
    data = {**FULL, **case.profile}
    for name in case.clear:
        data[name] = None
    return InvestorProfile(**data)


def judge(case, start: InvestorProfile, turn) -> tuple[bool, str]:
    """(עבר?, מה קרה בפועל)."""
    if turn.error:
        return False, turn.error[:80]
    problems, seen = [], []
    for name, expected in case.expect.items():
        value = getattr(turn.profile, name)
        unknown = name in turn.profile.unknown_fields
        seen.append(f"{name}={value}" + (" (לא יודע)" if unknown else ""))
        if expected == UNKNOWN:
            ok = value is None and unknown
        elif expected == UNCHANGED:
            ok = value == getattr(start, name) and unknown == (name in start.unknown_fields)
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            ok = value is not None and abs(float(value) - expected) < 0.01
        else:
            ok = value == expected
        if not ok:
            problems.append(name)
    for name in case.rejected_in_code:
        rejected = any(name in (c.result.get("rejected") or {}) for c in turn.calls if c.name == "update_profile")
        seen.append(f"נדחה בקוד={'כן' if rejected else 'לא'}")
        if not rejected:
            problems.append(f"{name} לא נדחה בקוד")
    tools = ",".join(turn.tool_names) or "בלי כלי"
    return not problems, f"{'; '.join(seen)} | כלים: {tools}"


def show_expected(case) -> str:
    parts = [f"{k}={v}" for k, v in case.expect.items()]
    parts += [f"{k} נדחה בקוד" for k in case.rejected_in_code]
    return ", ".join(parts)


def main(argv=None) -> int:
    utf8_console()
    parser = argparse.ArgumentParser(description="סט הערכה לראיון (Gemini אמיתי)")
    parser.add_argument("--repeat", type=int, default=1, help="כמה פעמים להריץ כל מקרה")
    parser.add_argument("--delay", type=float, default=4.0, help="השהיה בשניות בין מקרים (מגבלת קצב לדקה)")
    parser.add_argument("--only", default="", help="רק מקרים ששמם מכיל את הטקסט")
    args = parser.parse_args(argv)

    today = date.today()
    selected = [c for c in cases(today) if args.only in c.name]
    print(f"סט הערכה לראיון: {len(selected)} מקרים × {args.repeat} | מודל: {model_name()} | היום: {today}\n")
    rows, total_ok, total_runs, full_pass, llm_calls, errors = [], 0, 0, 0, 0, 0
    for case in selected:
        start = start_profile(case)
        history = [{"role": "assistant", "content": case.question}, {"role": "user", "content": case.answer}]
        # שגיאת תקשורת (429 שנשאר אחרי ההמתנות, רשת) לא נספרת ככישלון של המודל: היא מוצגת בנפרד
        ok_count, runs, last = 0, 0, ""
        for _ in range(args.repeat):
            turn = run_turn(history, start, today)
            llm_calls += turn.llm_calls
            ok, last = judge(case, start, turn)
            if turn.error:
                errors += 1
            else:
                runs += 1
                ok_count += ok
            if args.delay:
                time.sleep(args.delay)
        total_ok += ok_count
        total_runs += runs
        full_pass += runs > 0 and ok_count == runs
        status = "שגיאה" if runs == 0 else "עבר" if ok_count == runs else "נכשל"
        rows.append([case.name, f'"{case.answer}" → {show_expected(case)}', last, f"{status} {ok_count}/{runs}"])
    print_table(["מקרה", "מצופה", "בפועל (ריצה אחרונה)", "תוצאה"], rows, max_width=75)
    print(f"\nסיכום: {full_pass}/{len(selected)} מקרים עברו בכל הריצות. "
          f"ריצות שעברו: {total_ok}/{total_runs} ({pct(total_ok, total_runs)}), בלי ריצות שנפלו בתקשורת. "
          f"קריאות ל-LLM: {llm_calls}. שגיאות תקשורת: {errors}.")
    return 0 if full_pass == len(selected) and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
