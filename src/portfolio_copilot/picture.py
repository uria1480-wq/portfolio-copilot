"""תמונת המצב הפיננסית: מאחדת ראיון, מסמכים והחזקות למקום אחד. הכל בקוד."""
from portfolio_copilot.intake import IntakeAnswers

FUND_TYPE_GROUPS = {
    "pension": {"pension"},
    "study_fund": {"study_fund"},
    "gemel": {"provident", "provident_investment"},
}


def _latest_reports(reports: list[dict]) -> list[dict]:
    """הדוח העדכני ביותר לכל קופה. הרשימה מגיעה מהחדש לישן."""
    seen = {}
    for d in reports:
        s = d["summary"]
        seen.setdefault((s.get("provider"), s.get("fund_name"), s.get("fund_type")), s)
    return list(seen.values())


def _fund_total(latest: list[dict], types: set) -> float | None:
    values = [s["balance_end"] for s in latest if s.get("fund_type") in types and s.get("balance_end") is not None]
    return round(sum(values), 2) if values else None


def build_picture(answers: IntakeAnswers, holdings_value: float | None, reports: list[dict],
                  payslips: list[dict], price_errors: list[str] | None = None) -> dict:
    latest = _latest_reports(reports)
    income = answers.monthly_net_income
    if income is None and payslips:
        income = payslips[0]["summary"].get("net_to_bank")

    items, gaps = [], []

    def add(label, value, source):
        items.append({"label": label, "value": value, "source": source})

    add("כסף נזיל וחסכונות בבנק", answers.liquid_savings, "ראיון" if answers.liquid_savings is not None else None)
    add("תיק השקעות", holdings_value, "קובץ החזקות" if holdings_value is not None else None)
    for label, key, manual in (("קרן פנסיה", "pension", answers.pension_value),
                               ("קרן השתלמות", "study_fund", answers.study_fund_value)):
        doc_value = _fund_total(latest, FUND_TYPE_GROUPS[key])
        if doc_value is not None:
            add(label, doc_value, "דוח מהקופה")
        elif manual is not None:
            add(label, manual, "הזנה ידנית")
        else:
            add(label, None, None)
            gaps.append(f"לא הועלה דוח ל{label} ולא הוזן שווי")
    gemel = _fund_total(latest, FUND_TYPE_GROUPS["gemel"])
    if gemel is not None:
        add("קופת גמל", gemel, "דוח מהקופה")
    add("נכסים אחרים", answers.other_assets, "הזנה ידנית" if answers.other_assets is not None else None)

    if holdings_value is None:
        gaps.append("לא נטען תיק השקעות")
    for symbol in price_errors or []:
        gaps.append(f"לא נמצא מחיר עבור {symbol}")
    if income is None:
        gaps.append("חסרה הכנסה נטו")
    if not answers.monthly_expenses:
        gaps.append("חסרות הוצאות חודשיות, ולכן אי אפשר לחשב כמה חודשים מכוסים בכסף הנזיל")

    months = None
    if answers.monthly_expenses and answers.liquid_savings is not None:
        months = round(answers.liquid_savings / answers.monthly_expenses, 1)
    rate = round(answers.can_save_monthly / income, 3) if income and answers.can_save_monthly is not None else None
    known = [i["value"] for i in items if i["value"] is not None]
    return {
        "items": items,
        "total": round(sum(known), 2) if known else None,
        "monthly_net_income": income,
        "can_save_monthly": answers.can_save_monthly,
        "savings_rate": rate,
        "emergency_months": months,
        "gaps": gaps,
    }