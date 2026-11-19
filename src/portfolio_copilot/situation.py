"""שלב 2 "המצב שלי": מה מוצג, מאיזה מקור, ואיך הערך נראה. הכל בקוד, בלי מודל שפה.

קורא רק את InvestorProfile (נתוני הראיון). לא קורא אחזקות, מחירים, דוחות קרנות או תלושים,
ולא את תשובות הטופס הישן או את ההזנה הידנית הישנה.
"""
from portfolio_copilot.schemas import InvestorProfile

SOURCE_INTERVIEW = "ראיון"
EMPTY = "—"

# (שדה בפרופיל, תווית, סוג הערך). הסדר הוא סדר ההצגה.
SECTIONS = [
    ("עליך", [
        ("age", "גיל", "int"),
        ("marital_status", "מצב משפחתי", "text"),
        ("employment_status", "מצב תעסוקתי", "text"),
    ]),
    ("תזרים חודשי", [
        ("monthly_net_income", "הכנסה נטו חודשית", "money"),
        ("spouse_monthly_net_income", "הכנסת בן/בת זוג", "money"),
        ("monthly_expenses", "הוצאות חודשיות", "money"),
        ("monthly_debt_payments", "החזרי חובות בחודש", "money"),
        ("monthly_deposit", "כמה אפשר להפריש בחודש", "money"),
    ]),
    ("נכסים", [
        ("liquid_savings", "כסף נזיל וחסכונות בבנק", "money"),
        ("pension_balance", "קרן פנסיה", "money"),
        ("study_fund_balance", "קרן השתלמות", "money"),
        ("other_assets", "נכסים אחרים", "money"),
    ]),
    ("יעדים", [
        ("investment_goal", "יעד", "text"),
        ("investment_horizon_years", "אופק השקעה", "years"),
    ]),
]
ASSET_KEYS = ("liquid_savings", "pension_balance", "study_fund_balance", "other_assets")


def format_value(kind: str, value) -> str:
    """ערך לתצוגה. None הוא תמיד "—", ו-0 מוצג כ-0 (המשתמש אמר "אין")."""
    if value is None:
        return EMPTY
    if kind == "money":
        return f"₪{value:,.0f}"
    if kind == "years":
        return f"{value} שנים"
    return str(value)


def _row(key, label, kind, value, source, unknown=False) -> dict:
    status = "unknown" if unknown else "missing" if value is None else "known"
    return {"key": key, "label": label, "value": value, "display": format_value(kind, value),
            "source": source, "status": status}


def build_situation(profile: InvestorProfile) -> dict:
    """בונה את תמונת המצב לתצוגה מהפרופיל בלבד. כל ערך ידוע מסומן במקור "ראיון".
    שדה שהמשתמש אמר עליו "לא יודע" מוצג כ-"—" עם מקור "ראיון"."""
    sections, gaps = [], []
    for title, fields in SECTIONS:
        rows = []
        for key, label, kind in fields:
            if key == "spouse_monthly_net_income" and not profile.spouse_income_required():
                continue
            value = getattr(profile, key)
            if value is not None:
                rows.append(_row(key, label, kind, value, SOURCE_INTERVIEW))
            elif key in profile.unknown_fields:
                rows.append(_row(key, label, kind, None, SOURCE_INTERVIEW, unknown=True))
                gaps.append(f"{label}: אמרת שאתה לא יודע")
            else:
                rows.append(_row(key, label, kind, None, None))
                gaps.append(f"{label}: לא נאסף בראיון")
        sections.append({"title": title, "rows": rows})

    known = [r["value"] for s in sections for r in s["rows"] if r["key"] in ASSET_KEYS and r["value"] is not None]
    return {"sections": sections, "total": round(sum(known), 2) if known else None, "gaps": gaps}


def load_situation(store, user_id: int) -> dict:
    """קורא מה-Store את הפרופיל בלבד ומחזיר את תמונת המצב לתצוגה."""
    return build_situation(store.load_profile(user_id))
