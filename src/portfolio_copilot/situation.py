"""שלב 2 "המצב שלי": מה מוצג, מאיזה מקור, ואיך הערך נראה. הכל בקוד, בלי מודל שפה.

קורא רק את InvestorProfile (נתוני הראיון) ואת ה-Store (מסמכים והחזקות שהועלו).
לא קורא את IntakeAnswers ולא את ההזנה הידנית הישנה.
"""
from portfolio_copilot.agent_tools import _prices_for
from portfolio_copilot.picture import FUND_TYPE_GROUPS, _fund_total, _latest_reports
from portfolio_copilot.schemas import InvestorProfile

SOURCE_INTERVIEW = "ראיון"
SOURCE_DOCUMENT = "מסמך"
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
        ("holdings", "תיק השקעות", "money"),
        ("pension_balance", "קרן פנסיה", "money"),
        ("study_fund_balance", "קרן השתלמות", "money"),
        ("gemel", "קופת גמל", "money"),
        ("other_assets", "נכסים אחרים", "money"),
    ]),
    ("יעדים", [
        ("investment_goal", "יעד", "text"),
        ("investment_horizon_years", "אופק השקעה", "years"),
    ]),
]
ASSET_KEYS = ("liquid_savings", "holdings", "pension_balance", "study_fund_balance", "gemel", "other_assets")


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


def build_situation(profile: InvestorProfile, fund_reports: list[dict], payslips: list[dict],
                    holdings_value: float | None = None, has_holdings: bool = False,
                    price_errors: list[str] | None = None) -> dict:
    """בונה את תמונת המצב לתצוגה.

    נתון ממסמך גובר על נתון מהראיון (המסמך נבדק בקוד): הכנסה נטו מהתלוש האחרון, ויתרות פנסיה,
    השתלמות וגמל מהדוח האחרון של כל קופה. שדה שהמשתמש אמר עליו "לא יודע" מוצג כ-"—" עם מקור "ראיון".
    """
    latest = _latest_reports(fund_reports)
    from_docs = {
        "monthly_net_income": payslips[0]["summary"].get("net_to_bank") if payslips else None,
        "pension_balance": _fund_total(latest, FUND_TYPE_GROUPS["pension"]),
        "study_fund_balance": _fund_total(latest, FUND_TYPE_GROUPS["study_fund"]),
        "gemel": _fund_total(latest, FUND_TYPE_GROUPS["gemel"]),
        "holdings": holdings_value,
    }

    sections, gaps = [], []
    for title, fields in SECTIONS:
        rows = []
        for key, label, kind in fields:
            if key == "spouse_monthly_net_income" and not profile.spouse_income_required():
                continue
            doc_value = from_docs.get(key)
            if doc_value is not None:
                rows.append(_row(key, label, kind, doc_value, SOURCE_DOCUMENT))
                continue
            if key == "gemel":  # קופת גמל מגיעה רק ממסמך, ומוצגת רק אם יש
                continue
            if key == "holdings":
                rows.append(_row(key, label, kind, None, None))
                gaps.append("לא נמצאו מחירים לתיק ההשקעות" if has_holdings else "לא נטען קובץ החזקות")
                continue
            value = getattr(profile, key)
            if value is not None:
                rows.append(_row(key, label, kind, value, SOURCE_INTERVIEW))
            elif key in profile.unknown_fields:
                rows.append(_row(key, label, kind, None, SOURCE_INTERVIEW, unknown=True))
                gaps.append(f"{label}: אמרת שאתה לא יודע")
            else:
                rows.append(_row(key, label, kind, None, None))
                gaps.append(f"{label}: לא נאסף בראיון ולא נמצא במסמך")
        sections.append({"title": title, "rows": rows})

    for symbol in price_errors or []:
        gaps.append(f"לא נמצא מחיר עבור {symbol}")
    known = [r["value"] for s in sections for r in s["rows"] if r["key"] in ASSET_KEYS and r["value"] is not None]
    return {"sections": sections, "total": round(sum(known), 2) if known else None, "gaps": gaps}


def load_situation(store, user_id: int, fetch=None) -> dict:
    """אוסף מה-Store את הפרופיל, המסמכים וההחזקות, ומחזיר את תמונת המצב לתצוגה."""
    holdings = store.list_holdings(user_id)
    value, errors = None, []
    if holdings:
        prices, errors = _prices_for([h["symbol"] for h in holdings], fetch)
        if not errors:
            value = round(sum(h["quantity"] * prices[h["symbol"]] for h in holdings), 2)
    return build_situation(store.load_profile(user_id), store.list_documents(user_id, "fund_report"),
                           store.list_documents(user_id, "payslip"), value, bool(holdings), errors)
