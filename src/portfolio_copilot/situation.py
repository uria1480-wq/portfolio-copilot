"""שלב 2 "המצב שלי": מה מוצג, מאיזה מקור, ואיך הערך נראה. הכל בקוד, בלי מודל שפה.

קורא את InvestorProfile (נתוני הראיון) ואת היסטוריית הדיווחים החודשיים שמועברת מבחוץ (בלי גישה ל-DB).
לא קורא אחזקות, מחירים, דוחות קרנות או תלושים, ולא את תשובות הטופס הישן או את ההזנה הידנית הישנה.
הפרופיל לא משתנה: מה שנוסף מהדיווחים מוצג בנפרד, עם מקור "דיווח חודשי".
"""
from portfolio_copilot.schemas import InvestorProfile

SOURCE_INTERVIEW = "ראיון"
SOURCE_MONTHLY = "דיווח חודשי"
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
            "source": source, "status": status, "added": None, "added_source": None, "detail": None}


def _sum(history: list[dict], key: str, fallback: str) -> float:
    """סכום שדה מכל הדיווחים. רשומות ישנות בלי השדה המשותף נקראות מהשדה שלך."""
    return round(sum(float(e.get(key, e.get(fallback)) or 0) for e in history), 2)


def monthly_additions(history: list[dict]) -> dict:
    """כמה נוסף מהדיווחים החודשיים: לנזיל כל מה שהופקד, לפנסיה ולהשתלמות ההפקדות של שני בני הזוג."""
    return {
        "liquid_savings": _sum(history, "set_aside", "set_aside"),
        "pension_balance": _sum(history, "total_pension", "pension_contributions"),
        "study_fund_balance": _sum(history, "total_study_fund", "study_fund_contributions"),
    }


def _add_monthly(row: dict, added: float) -> None:
    """מוסיף לשורה את מה שנוסף מהדיווחים. הבסיס מהראיון נשאר במקור "ראיון", והתוספת מסומנת בנפרד.
    אם הבסיס חסר, לא ממציאים סכום: הערך נשאר ריק, ורק ההסבר מראה מה נוסף."""
    row["added"], row["added_source"] = added, SOURCE_MONTHLY
    if row["value"] is None:
        row["detail"] = f"+{format_value('money', added)} מדיווחים חודשיים (הבסיס מהראיון חסר)"
        return
    base = row["value"]
    row["value"] = round(base + added, 2)
    row["display"] = format_value("money", row["value"])
    row["detail"] = f"{format_value('money', base)} מהראיון + {format_value('money', added)} מדיווחים חודשיים"


def build_situation(profile: InvestorProfile, history: list[dict] | None = None) -> dict:
    """בונה את תמונת המצב לתצוגה מהפרופיל, ומוסיף לנזיל, לפנסיה ולהשתלמות את מה שהופקד בדיווחים החודשיים.
    כל ערך מהפרופיל מסומן במקור "ראיון". שדה שהמשתמש אמר עליו "לא יודע" מוצג כ-"—" עם מקור "ראיון"."""
    additions = monthly_additions(history or [])
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
            if additions.get(key):
                _add_monthly(rows[-1], additions[key])
        sections.append({"title": title, "rows": rows})

    known = [r["value"] for s in sections for r in s["rows"] if r["key"] in ASSET_KEYS and r["value"] is not None]
    return {"sections": sections, "total": round(sum(known), 2) if known else None, "gaps": gaps}


def load_situation(store, user_id: int, history: list[dict] | None = None) -> dict:
    """קורא מה-Store את הפרופיל, ומחזיר את תמונת המצב לתצוגה. ההיסטוריה מועברת מבחוץ."""
    return build_situation(store.load_profile(user_id), history)
