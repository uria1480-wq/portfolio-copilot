"""מריץ את סט ההערכה להצעה (קוד בלבד, בלי LLM, בלי עלות).

הרצה:  uv run python evals/run_proposal.py
יציאה עם קוד 1 אם מקרה כלשהו נכשל.
"""
import sys
from datetime import date

from common import pct, print_table, utf8_console
from proposal_cases import BASE, CASES

from portfolio_copilot.proposal import build_proposal
from portfolio_copilot.restrictions import ASSET_CLASSES
from portfolio_copilot.schemas import InvestorProfile

TODAY = date(2026, 11, 22)
TOLERANCE = 0.01


def close(a, b) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= TOLERANCE


def actual_values(p) -> dict:
    """מה שהקוד חישב, באותם מפתחות כמו expect."""
    safety, capital = p.safety, p.capital
    return {
        "mix": tuple(line.percent for line in capital.allocation) if capital else None,
        "equity": capital.equity_percent if capital else None,
        "pension": p.pension.pension_track if p.pension else None,
        "emergency_months": safety.emergency_target_months if safety else None,
        "shortfall": safety.shortfall if safety else None,
        "months_to_fill": safety.months_to_fill if safety else None,
        "surplus": capital.liquid_surplus if capital else None,
        "debt_ratio": safety.debt_ratio if safety else None,
        "reduce_debt": safety.reduce_debt_first if safety else None,
        "no_capital": capital is None,
        "no_safety": safety is None,
        "missing": p.missing,
        "reason": p.reasons,
        "note": p.notes,
        "step": safety.steps if safety else [],
    }


def check(key, expected, actual) -> bool:
    if key == "mix":
        return actual is not None and all(close(e, a) for e, a in zip(expected, actual))
    if key in ("equity", "shortfall", "surplus", "debt_ratio"):
        return close(expected, actual)
    if key == "missing":
        return all(f in actual for f in expected)
    if key in ("reason", "note", "step"):
        return any(expected in text for text in actual)
    return expected == actual


def show(key, value) -> str:
    if key == "mix" and value is not None:
        return "/".join(f"{v:g}" for v in value)
    if key in ("reason", "note", "step") and isinstance(value, list):
        return "…" if value else "[]"
    return str(value)


def run_case(case) -> tuple[bool, str, str]:
    data = case.profile if case.replace_base else {**BASE, **case.profile}
    proposal = build_proposal(InvestorProfile(**data), TODAY)
    actual = actual_values(proposal)
    failed = [k for k, v in case.expect.items() if not check(k, v, actual[k])]
    expected_text = ", ".join(f"{k}={show(k, v)}" for k, v in case.expect.items())
    actual_text = ", ".join(f"{k}={show(k, actual[k])}" for k in (failed or case.expect))
    return not failed, expected_text, ("✓ " if not failed else "✗ ") + actual_text


def main() -> int:
    utf8_console()
    print(f"סט הערכה להצעה: {len(CASES)} מקרים. תמהיל = {' / '.join(ASSET_CLASSES)}\n")
    rows, passed = [], 0
    for case in CASES:
        ok, expected, actual = run_case(case)
        passed += ok
        rows.append([case.name, expected, actual, "עבר" if ok else "נכשל"])
    print_table(["מקרה", "מצופה", "בפועל (בכישלון: רק מה שנכשל)", "תוצאה"], rows, max_width=80)
    print(f"\nסיכום: {passed}/{len(CASES)} עברו ({pct(passed, len(CASES))}).")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
