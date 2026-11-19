"""שלב 2 "המצב שלי": מה מוצג, מאיזה מקור, ואיך הערך נראה. הכל בקוד, בלי מודל שפה.

קורא רק את InvestorProfile (נתוני הראיון). לא קורא אחזקות, מחירים, דוחות קרנות או תלושים,
ולא את IntakeAnswers או את ההזנה הידנית הישנה.
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


# שדה בתמונת המצב -> שם השדה ב-IntakeAnswers שהניתוח מקבל
ANSWER_FIELDS = {
    "monthly_net_income": "monthly_net_income",
    "monthly_expenses": "monthly_expenses",
    "monthly_deposit": "can_save_monthly",
    "liquid_savings": "liquid_savings",
    "monthly_debt_payments": "monthly_debt_payments",
    "pension_balance": "pension_value",
    "study_fund_balance": "study_fund_value",
    "other_assets": "other_assets",
}


def situation_values(situation: dict) -> dict:
    """ערך לכל שדה שמוצג בתמונת המצב. שדה לא ידוע או חסר הוא None, לא 0."""
    return {r["key"]: r["value"] for s in situation["sections"] for r in s["rows"]}


def analysis_answer_values(situation: dict) -> dict:
    """הערכים המספריים לניתוח (שלב 3), בדיוק כפי שהם מוצגים בשלב 2."""
    values = situation_values(situation)
    return {answer_key: values.get(key) for key, answer_key in ANSWER_FIELDS.items()}


def analysis_input(situation: dict) -> dict:
    """תמונת המצב של שלב 2 במבנה שהניתוח מקבל: אותם ערכים, אותם מקורות ואותם פערים.
    יחסים (חודשי חירום, שיעור חיסכון) מחושבים רק כששני הערכים ידועים, אחרת None."""
    values = situation_values(situation)
    items = [{"label": r["label"], "value": r["value"], "source": r["source"]}
             for s in situation["sections"] for r in s["rows"] if r["key"] in ASSET_KEYS]
    income, deposit = values.get("monthly_net_income"), values.get("monthly_deposit")
    expenses, liquid = values.get("monthly_expenses"), values.get("liquid_savings")
    return {
        "items": items,
        "total": situation["total"],
        "monthly_net_income": income,
        "can_save_monthly": deposit,
        "savings_rate": round(deposit / income, 3) if income and deposit is not None else None,
        "emergency_months": round(liquid / expenses, 1) if expenses and liquid is not None else None,
        "gaps": list(situation["gaps"]),
    }


def load_situation(store, user_id: int) -> dict:
    """קורא מה-Store את הפרופיל בלבד ומחזיר את תמונת המצב לתצוגה."""
    return build_situation(store.load_profile(user_id))
