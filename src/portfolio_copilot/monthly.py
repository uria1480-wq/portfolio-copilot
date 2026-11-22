"""הדיווח החודשי: חלוקת ההשקעה החודשית (קודם קרן החירום, אחר כך לפי התמהיל), מעקב קרן החירום על פני
ההיסטוריה, ברירת המחדל לאחוז מהראיון, ושורת ההיסטוריה.

קוד טהור, בלי מודל שפה. משתמש בחוקי ההצעה (proposal.py) ובהגבלות (restrictions.py). אין מכירות.
"""
from datetime import date

from pydantic import BaseModel, Field

from portfolio_copilot.proposal import _emergency, _emergency_reason, _mix, _needs, _required_ok, _split
from portfolio_copilot.restrictions import ASSET_CLASSES, MONEY_MARKET, blocked_classes, emergency_asset_class
from portfolio_copilot.schemas import InvestorProfile, format_money


class MonthlyLine(BaseModel):
    asset_class: str
    amount: float


class MonthlyAllocation(BaseModel):
    as_of: date
    deposit: float
    emergency_amount: float = 0.0          # להשלמת קרן החירום
    emergency_asset_class: str = MONEY_MARKET  # לאן הולכת השלמת הקרן: כספית, או התחליף שלה אם היא אסורה
    lines: list[MonthlyLine] | None = None  # השאר לפי התמהיל. None = לא חושב (חסרים נתונים)
    unallocated: float = 0.0                # מה שלא חולק כי חסר תמהיל
    missing: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def amount_from_percent_of_net(profile: InvestorProfile, percent) -> tuple[float, str]:
    """אחוז מהנטו החודשי שבפרופיל -> סכום בשקלים, מחושב בקוד (לא במודל). מחזיר (סכום, נימוק).
    ValueError אם האחוז לא בין 0 (לא כולל) ל-100, או שאין בפרופיל נטו חיובי."""
    if isinstance(percent, bool):
        raise ValueError("percent_of_net צריך להיות מספר, למשל 10")
    try:
        pct = float(percent)
    except (TypeError, ValueError):
        raise ValueError("percent_of_net צריך להיות מספר, למשל 10")
    if not 0 < pct <= 100:
        raise ValueError("האחוז מהנטו צריך להיות גדול מ-0 ועד 100")
    net = profile.monthly_net_income
    if not net or net <= 0:
        raise ValueError("בפרופיל אין הכנסה נטו חודשית, ולכן אי אפשר לחשב אחוז מהנטו. בקש סכום בשקלים")
    amount = round(net * pct / 100, 2)
    return amount, f"סכום להשקעה: {pct:g}% מהנטו שלך בפרופיל ({format_money(net)}) = {format_money(amount)}."


def emergency_deposited(history: list[dict]) -> float:
    """סך מה שכבר הופנה לקרן החירום בדיווחים חודשיים קודמים (מההיסטוריה השמורה).
    רשומות ישנות בלי allocation נספרות כ-0."""
    total = sum(float((e.get("allocation") or {}).get("emergency_amount") or 0) for e in history)
    return round(total, 2)


def allocate_monthly(profile: InvestorProfile, deposit: float, today: date | None = None,
                     already_in_emergency: float = 0.0) -> MonthlyAllocation:
    """מחלק הפקדה חודשית: קודם משלימים חוסר בקרן החירום (לכספית, או לתחליף שלה אם היא אסורה),
    והשאר לפי התמהיל של build_proposal.
    החוסר = יעד פחות הנזיל בפרופיל פחות מה שכבר הופנה לקרן בדיווחים קודמים (already_in_emergency), ולא פחות מ-0.
    הסכומים מעוגלים כך שהסכום הכולל שווה בדיוק להפקדה. אין מכירות."""
    today = today or date.today()
    if deposit is None or deposit <= 0:
        raise ValueError("סכום ההשקעה החודש חייב להיות חיובי")
    deposit = round(float(deposit), 2)
    already = round(max(0.0, float(already_in_emergency or 0)), 2)
    missing: list[str] = []
    reasons: list[str] = []
    need = _needs(profile, missing)

    emergency = 0.0
    emergency_class = emergency_asset_class(blocked_classes(profile))
    if need("monthly_expenses", "liquid_savings"):
        months, target, profile_shortfall = _emergency(profile)
        reasons.append(_emergency_reason(profile, months, target))
        shortfall = round(max(0.0, profile_shortfall - already), 2)
        if already and profile_shortfall:
            reasons.append(f"בדיווחים קודמים כבר הופנו {format_money(already)} לקרן החירום, "
                           f"ולכן החוסר שנשאר הוא {format_money(shortfall)}.")
        emergency = round(min(shortfall, deposit), 2)
        if emergency:
            reasons.append(f"חסרים {format_money(shortfall)} בקרן החירום, ולכן {format_money(emergency)} מההפקדה הולכים קודם ל{emergency_class}.")
        else:
            reasons.append("קרן החירום מלאה, ולכן כל ההפקדה מתחלקת לפי התמהיל.")
    else:
        reasons.append("אי אפשר לבדוק את קרן החירום בלי הוצאות חודשיות וכסף נזיל, ולכן לא הופרש לה סכום.")

    rest = round(deposit - emergency, 2)
    lines, unallocated = None, 0.0
    if not _required_ok(profile, need, missing):
        unallocated = rest
        if rest:
            reasons.append(f"{format_money(rest)} לא חולקו: חסרים גיל, רמת סיכון מאושרת או אופק.")
    elif rest:
        _, _, pct = _mix(profile, reasons)
        parts = _split(rest, pct)
        lines = [MonthlyLine(asset_class=k, amount=parts[k]) for k in ASSET_CLASSES]
        reasons.append(f"{format_money(rest)} מתחלקים לפי התמהיל.")
    else:
        lines = []
    return MonthlyAllocation(as_of=today, deposit=deposit, emergency_amount=emergency,
                             emergency_asset_class=emergency_class, lines=lines,
                             unallocated=unallocated, missing=missing, reasons=reasons)


class PercentDefault(BaseModel):
    """ברירת המחדל לשדה האחוז בדיווח החודשי. value=None: השדה ריק, ו-explanation אומר למה."""
    value: float | None = None
    explanation: str


def default_savings_percent(profile: InvestorProfile) -> PercentDefault:
    """ברירת המחדל לאחוז ההשקעה החודשי מהראיון, עד ספרה עשרונית אחת.
    נשוי/ידוע בציבור עם הכנסת בן/בת זוג ידועה: monthly_deposit / (monthly_net_income + spouse_monthly_net_income).
    אחרת: monthly_deposit / monthly_net_income. ריק (עם הסבר) אם חסר נתון, הנטו 0 או שהתוצאה מעל 100%."""
    deposit, net = profile.monthly_deposit, profile.monthly_net_income
    combined = profile.is_partnered() and profile.spouse_monthly_net_income is not None
    base = "הנטו המשותף" if combined else "הנטו שלך"
    if deposit is None:
        return PercentDefault(explanation="השדה ריק: בראיון לא נמסר כמה אפשר להפריש בחודש. הזן אחוז או סכום.")
    if net is None:
        return PercentDefault(explanation="השדה ריק: בראיון לא נמסרה הכנסה נטו חודשית. הזן אחוז או סכום.")
    total = round(net + (profile.spouse_monthly_net_income if combined else 0), 2)
    if total <= 0:
        return PercentDefault(explanation=f"השדה ריק: {base} בראיון הוא ₪0, ואי אפשר לחשב ממנו אחוז.")
    pct = round(deposit / total * 100, 1)
    if pct > 100:
        return PercentDefault(explanation=f"השדה ריק: ההפקדה מהראיון ({format_money(deposit)}) גבוהה מ{base} "
                                          f"({format_money(total)}). הזן אחוז או סכום.")
    if combined:
        how = (f"{format_money(deposit)} מתוך נטו משותף של {format_money(total)} ({format_money(net)} שלך + "
               f"{format_money(profile.spouse_monthly_net_income)} של בן/בת הזוג), לפי הראיון. "
               "האחוז יחול על הנטו המשותף רק אם תזין גם את נטו בן/בת הזוג החודש.")
    else:
        how = f"{format_money(deposit)} מתוך נטו של {format_money(total)}, לפי הראיון."
    return PercentDefault(value=pct, explanation=how + " אפשר לשנות.")


class MonthlyReport(BaseModel):
    """דיווח חודשי אחד. נשמר כ-JSON בהיסטוריה: הערכים שלך, של בן/בת הזוג (אם הוזנו) והסכומים המשותפים."""
    period: str
    # שלך
    net: float
    pension_contributions: float = 0.0
    study_fund_contributions: float = 0.0
    # בן/בת הזוג (None = לא הוזן). לא נשמר בפרופיל
    partner_net: float | None = None
    partner_pension: float | None = None
    partner_study_fund: float | None = None
    # משותף: שלך + בן/בת הזוג
    household_net: float
    total_pension: float
    total_study_fund: float
    percent_base: str | None = None        # "נטו שלך" או "נטו משותף", כשהסכום הוזן באחוזים
    set_aside: float
    free_to_spend: float
    total_saved_this_month: float
    allocation: MonthlyAllocation


BASE_OWN = "נטו שלך"
BASE_COMBINED = "נטו משותף"


def _non_negative(*values):
    if any(v is not None and v < 0 for v in values):
        raise ValueError("הנטו וההפקדות לפנסיה ולהשתלמות לא יכולים להיות שליליים")


def monthly_report(profile: InvestorProfile, net: float, pension: float | None, study_fund: float | None,
                   amount_mode: str, amount_value: float, today: date | None = None,
                   partner_net: float | None = None, already_in_emergency: float = 0.0,
                   partner_pension: float | None = None, partner_study_fund: float | None = None) -> MonthlyReport:
    """הדיווח החודשי: כמה מושקע החודש (סכום קבוע או אחוז), ואיך הוא מתחלק (allocate_monthly).
    amount_mode הוא "fixed" (שקלים) או "percent" (25 = 25%). האחוז חל על הנטו שלך,
    ואם הוזן נטו בן/בת הזוג, על הנטו המשותף. פנסיה והשתלמות מסוכמות לשני בני הזוג. אין מכירות."""
    today = today or date.today()
    if not profile.is_partnered():
        # השדות לא מוצגים למי שלא נשוי/בזוגיות, אז ערכים שנשארו בהם לא נספרים
        partner_net = partner_pension = partner_study_fund = None
    if not net or net <= 0:
        raise ValueError("הזן כמה נכנס נטו החודש")
    _non_negative(pension, study_fund, partner_net, partner_pension, partner_study_fund)
    if not amount_value or amount_value <= 0:
        raise ValueError("הזן כמה להשקיע החודש: סכום בשקלים או אחוז מהנטו")
    combined = partner_net is not None
    household = round(net + (partner_net or 0), 2)
    base_label = BASE_COMBINED if combined else BASE_OWN
    if amount_mode == "percent":
        if amount_value > 100:
            raise ValueError("אחוז ההשקעה לא יכול לעלות על 100%")
        deposit = round(household * amount_value / 100, 2)
    elif amount_mode == "fixed":
        deposit = round(float(amount_value), 2)
    else:
        raise ValueError(f"אופן חישוב לא מוכר: {amount_mode}")
    if deposit > household:
        raise ValueError(f"הסכום להשקעה ({format_money(deposit)}) גבוה מה{base_label} שנכנס החודש ({format_money(household)})")
    allocation = allocate_monthly(profile, deposit, today, already_in_emergency)
    if amount_mode == "percent":
        detail = (f"{format_money(net)} שלך + {format_money(partner_net)} של בן/בת הזוג = {format_money(household)}" if combined
                  else format_money(net))
        allocation.reasons.insert(0, f"סכום להשקעה: {amount_value:g}% מה{base_label} ({detail}) = {format_money(deposit)}.")
    own_pension, own_study = round(pension or 0, 2), round(study_fund or 0, 2)
    p_pension = round(partner_pension, 2) if partner_pension is not None else None
    p_study = round(partner_study_fund, 2) if partner_study_fund is not None else None
    total_pension = round(own_pension + (p_pension or 0), 2)
    total_study = round(own_study + (p_study or 0), 2)
    return MonthlyReport(period=today.strftime("%Y-%m"), net=round(net, 2), pension_contributions=own_pension,
                         study_fund_contributions=own_study,
                         partner_net=round(partner_net, 2) if combined else None,
                         partner_pension=p_pension, partner_study_fund=p_study,
                         household_net=household, total_pension=total_pension, total_study_fund=total_study,
                         percent_base=base_label if amount_mode == "percent" else None,
                         set_aside=deposit, free_to_spend=round(household - deposit, 2),
                         total_saved_this_month=round(deposit + total_pension + total_study, 2), allocation=allocation)


def history_row(event: dict) -> dict:
    """שורה בטבלת ההיסטוריה מדיווח שמור: סכומים משותפים. רשומות ישנות בלי השדות המשותפים נקראות מהשדות שלך."""
    allocation = event.get("allocation") or {}
    return {
        "period": event.get("period") or "",
        "household_net": event.get("household_net", event.get("net")),
        "total_pension": event.get("total_pension", event.get("pension_contributions")),
        "total_study_fund": event.get("total_study_fund", event.get("study_fund_contributions")),
        "set_aside": event.get("set_aside"),
        "emergency": allocation.get("emergency_amount") if allocation else None,
    }
