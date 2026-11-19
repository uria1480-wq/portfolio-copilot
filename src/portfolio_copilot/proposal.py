"""הצעה ("קבל הצעה"): קרן חירום וחובות, תמהיל להון הקיים ולהפקדה החודשית, ומסלול לפנסיה ולהשתלמות.

קוד טהור: הכל מחושב כאן לפי חוקים קבועים, בלי מודל שפה. ההצעה בסוגי נכסים בלבד, לא מניות או מוצרים.
כל החוקים מסתמכים רק על InvestorProfile. שדה חסר לא מנוחש: החלק שתלוי בו לא מחושב, והשדה מופיע ב-missing.
"""
import math
from datetime import date

from pydantic import BaseModel, Field

from portfolio_copilot.schemas import PARTNERED_STATUSES, InvestorProfile

# ---------- קבועים (לשנות כאן) ----------
# חוק 1: קרן חירום, בחודשי הוצאות
EMERGENCY_MONTHS_TWO_INCOMES = 3   # שכיר/ה עם בן/בת זוג שיש להם הכנסה נטו חיובית
EMERGENCY_MONTHS_DEFAULT = 6
SALARIED_STATUS = "שכיר/ה"

# חוק 2: חוב
DEBT_TO_INCOME_LIMIT = 0.30

# חוק 3: אחוז מניות לפי אופק (עד כמה שנים, כולל) ורמת סיכון. None = מעל הסף האחרון
EQUITY_PCT_BY_HORIZON = [
    (3, {"שמרני": 0, "מאוזן": 10, "אגרסיבי": 20}),
    (7, {"שמרני": 20, "מאוזן": 40, "אגרסיבי": 60}),
    (15, {"שמרני": 30, "מאוזן": 55, "אגרסיבי": 75}),
    (None, {"שמרני": 40, "מאוזן": 65, "אגרסיבי": 90}),
]
HORIZON_LABELS = {3: "עד 3 שנים", 7: "4 עד 7 שנים", 15: "8 עד 15 שנים", None: "מעל 15 שנים"}

# חוק 4: תקרת גיל
AGE_CAP_BASE = 110  # מניות לא יעלו על 110 פחות הגיל

# חוק 5: חלוקת הלא-מניות
SHORT_HORIZON_YEARS = 3
BONDS_SHARE_SHORT = 0.40   # מהלא-מניות, באופק עד 3 שנים. השאר כספית
BONDS_SHARE_LONG = 0.70    # מהלא-מניות, באופק ארוך יותר. השאר כספית

# מחלקות הנכסים, בסדר ההצגה
US_EQUITY = 'מדד מניות ארה"ב'
WORLD_EQUITY = "מדד מניות עולמי"
GOV_BONDS = 'אג"ח ממשלתי'
CORP_BONDS = 'אג"ח קונצרני'
MONEY_MARKET = "כספית"
ASSET_CLASSES = (US_EQUITY, WORLD_EQUITY, GOV_BONDS, CORP_BONDS, MONEY_MARKET)

# חוק 7: פנסיה והשתלמות
PENSION_ALL_EQUITY_UNDER_AGE = 40
PENSION_ALL_EQUITY_LABEL = "100% מנייתי"
PENSION_TRACKS = [(80, "מנייתי"), (40, "כללי"), (0, 'אג"ח/שמרני')]  # אחוז מניות מינימלי -> מסלול

# חוק 8: ריכוז בנדל"ן או בנכסים אחרים
OTHER_ASSETS_CONCENTRATION = 0.50


# ---------- פלט ----------
class AllocationLine(BaseModel):
    asset_class: str
    percent: float
    existing_amount: float | None = None  # מהעודף הנזיל
    monthly_amount: float | None = None   # מההפקדה החודשית


class SafetySection(BaseModel):
    emergency_target_months: int | None = None
    emergency_target_amount: float | None = None
    current_months: float | None = None
    shortfall: float | None = None
    months_to_fill: int | None = None
    debt_ratio: float | None = None
    reduce_debt_first: bool = False
    steps: list[str] = Field(default_factory=list)


class CapitalSection(BaseModel):
    equity_percent: float
    allocation: list[AllocationLine]
    liquid_surplus: float | None = None
    monthly_deposit: float | None = None


class PensionSection(BaseModel):
    pension_track: str
    study_fund_track: str


class Proposal(BaseModel):
    as_of: date
    missing: list[str] = Field(default_factory=list)
    safety: SafetySection | None = None
    capital: CapitalSection | None = None
    pension: PensionSection | None = None
    notes: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


# ---------- חוקים ----------
def _money(x: float) -> str:
    return f"₪{x:,.0f}"


def emergency_target_months(profile: InvestorProfile) -> int:
    """חוק 1: 3 חודשים לשכיר/ה עם בן/בת זוג שמכניסים נטו חיובי. אחרת 6."""
    two_incomes = (profile.employment_status == SALARIED_STATUS
                   and profile.marital_status in PARTNERED_STATUSES
                   and (profile.spouse_monthly_net_income or 0) > 0)
    return EMERGENCY_MONTHS_TWO_INCOMES if two_incomes else EMERGENCY_MONTHS_DEFAULT


def horizon_bucket(years: int) -> int | None:
    for limit, _ in EQUITY_PCT_BY_HORIZON:
        if limit is None or years <= limit:
            return limit
    return None


def equity_percent(risk_level: str, horizon_years: int, age: int) -> tuple[float, float, int | None]:
    """חוקים 3-4: מחזיר (אחוז מניות סופי, אחוז מהטבלה, הדלי של האופק)."""
    bucket = horizon_bucket(horizon_years)
    table_pct = dict(EQUITY_PCT_BY_HORIZON)[bucket][risk_level]
    return float(min(table_pct, max(0, AGE_CAP_BASE - age))), float(table_pct), bucket


def allocation_percents(equity_pct: float, horizon_years: int) -> dict[str, float]:
    """חוק 5: מחלק את 100% בין מחלקות הנכסים. הסכום תמיד 100."""
    rest = 100 - equity_pct
    bonds_share = BONDS_SHARE_SHORT if horizon_years <= SHORT_HORIZON_YEARS else BONDS_SHARE_LONG
    bonds = rest * bonds_share
    pct = {
        US_EQUITY: round(equity_pct / 2, 2),
        WORLD_EQUITY: round(equity_pct / 2, 2),
        GOV_BONDS: round(bonds / 2, 2),
        CORP_BONDS: round(bonds / 2, 2),
    }
    pct[MONEY_MARKET] = round(100 - sum(pct.values()), 2)
    return pct


def _split(amount: float, pct: dict[str, float]) -> dict[str, float]:
    """מחלק סכום לפי האחוזים. תיקון העיגול נכנס לכספית, כך שהסכום שווה בדיוק."""
    parts = {k: round(amount * p / 100, 2) for k, p in pct.items()}
    parts[MONEY_MARKET] = round(parts[MONEY_MARKET] + amount - sum(parts.values()), 2)
    return parts


def pension_track(age: int, equity_pct: float) -> str:
    """חוק 7: מתחת לגיל 40, 100% מנייתי. מגיל 40, לפי אחוז המניות."""
    if age < PENSION_ALL_EQUITY_UNDER_AGE:
        return PENSION_ALL_EQUITY_LABEL
    return next(label for minimum, label in PENSION_TRACKS if equity_pct >= minimum)


def _emergency(profile: InvestorProfile) -> tuple[int, float, float]:
    """חוק 1: (יעד בחודשים, יעד בשקלים, חסר בשקלים). דורש monthly_expenses ו-liquid_savings."""
    months = emergency_target_months(profile)
    target = round(months * profile.monthly_expenses, 2)
    return months, target, round(max(0.0, target - profile.liquid_savings), 2)


def _emergency_reason(profile: InvestorProfile, months: int, target: float) -> str:
    why = ("שכיר/ה ויש הכנסה נוספת של בן/בת הזוג" if months == EMERGENCY_MONTHS_TWO_INCOMES
           else "אין שתי הכנסות קבועות במשק הבית")
    return (f"קרן חירום: יעד {months} חודשי הוצאות ({why}), כלומר {_money(target)} "
            f"לפי הוצאות של {_money(profile.monthly_expenses)} בחודש. יש היום {_money(profile.liquid_savings)}.")


def _needs(profile: InvestorProfile, missing: list[str]):
    """מחזיר need(*fields): בודק שהשדות ידועים, ומוסיף ל-missing את מה שחסר."""
    def need(*fields):
        absent = [f for f in fields if getattr(profile, f) is None]
        for f in absent:
            if f not in missing:
                missing.append(f)
        return not absent
    return need


def _required_ok(profile: InvestorProfile, need, missing: list[str]) -> bool:
    """גיל, רמת סיכון מאושרת ואופק. בלי אחד מהם אין תמהיל."""
    ok = need("age", "recommended_risk_level", "investment_horizon_years")
    if profile.recommended_risk_level is not None and not profile.risk_confirmed:
        missing.append("risk_confirmed")
        ok = False
    return ok


def _mix(profile: InvestorProfile, reasons: list[str]) -> tuple[float, float, dict[str, float]]:
    """חוקים 3-5: (אחוז מניות אחרי תקרת גיל, אחוז מניות מהטבלה, אחוז לכל מחלקה). מוסיף הסברים."""
    eq, table_pct, bucket = equity_percent(profile.recommended_risk_level, profile.investment_horizon_years,
                                           profile.age)
    reasons.append(f"מניות: {table_pct:.0f}% לפי רמת סיכון {profile.recommended_risk_level} "
                   f"ואופק {HORIZON_LABELS[bucket]} ({profile.investment_horizon_years} שנים).")
    if eq < table_pct:
        reasons.append(f"תקרת גיל: {AGE_CAP_BASE} פחות גיל {profile.age} = {AGE_CAP_BASE - profile.age}%, "
                       f"ולכן המניות בהון הנזיל ובהפקדות הוגבלו ל-{eq:.0f}%.")
    pct = allocation_percents(eq, profile.investment_horizon_years)
    bonds_share = BONDS_SHARE_SHORT if profile.investment_horizon_years <= SHORT_HORIZON_YEARS else BONDS_SHARE_LONG
    reasons.append(f'שאר {100 - eq:g}%: אג"ח {bonds_share:.0%} (חצי ממשלתי, חצי קונצרני) וכספית '
                   f'{1 - bonds_share:.0%}. המניות מתחלקות שווה בין ארה"ב לעולם.')
    return eq, table_pct, pct


def build_proposal(profile: InvestorProfile, today: date | None = None) -> Proposal:
    today = today or date.today()
    missing: list[str] = []
    reasons: list[str] = []
    notes: list[str] = []
    need = _needs(profile, missing)

    # --- חלק 1: ביטחון ---
    safety = SafetySection()
    target_amount = None
    if need("monthly_expenses", "liquid_savings"):
        months, target_amount, shortfall = _emergency(profile)
        safety.emergency_target_months = months
        safety.emergency_target_amount = target_amount
        safety.shortfall = shortfall
        if profile.monthly_expenses > 0:
            safety.current_months = round(profile.liquid_savings / profile.monthly_expenses, 1)
        reasons.append(_emergency_reason(profile, months, target_amount))
        if shortfall > 0:
            safety.steps.append(f"להשלים קרן חירום: חסרים {_money(shortfall)}. ההפקדות הראשונות הולכות לכספית.")
            if need("monthly_deposit") and profile.monthly_deposit > 0:
                safety.months_to_fill = math.ceil(shortfall / profile.monthly_deposit)
                reasons.append(f"השלמת קרן החירום: {_money(shortfall)} / {_money(profile.monthly_deposit)} בחודש = "
                               f"כ-{safety.months_to_fill} חודשים.")
        else:
            reasons.append("קרן החירום מלאה, ולכן מה שמעבר לה הוא עודף נזיל שאפשר להשקיע.")

    if need("monthly_debt_payments", "monthly_net_income") and profile.monthly_net_income > 0:
        ratio = round(profile.monthly_debt_payments / profile.monthly_net_income, 3)
        safety.debt_ratio = ratio
        safety.reduce_debt_first = ratio > DEBT_TO_INCOME_LIMIT
        reasons.append(f"חובות: החזר של {_money(profile.monthly_debt_payments)} מתוך נטו של "
                       f"{_money(profile.monthly_net_income)} הוא {ratio:.0%} (הסף {DEBT_TO_INCOME_LIMIT:.0%}).")
        if safety.reduce_debt_first:
            safety.steps.append("להקטין חוב לפני השקעה: ההחזר החודשי גבוה מ-30% מהנטו.")

    # --- חלקים 2-3: דורשים גיל, רמת סיכון מאושרת ואופק ---
    capital = pension = None
    if _required_ok(profile, need, missing):
        eq, table_pct, pct = _mix(profile, reasons)

        surplus = None
        if target_amount is not None:
            surplus = round(max(0.0, profile.liquid_savings - target_amount), 2)
            reasons.append(f"עודף נזיל: {_money(profile.liquid_savings)} פחות יעד קרן החירום {_money(target_amount)} "
                           f"= {_money(surplus)}." + (" אין עודף, ולכן אין פריסה של הון קיים." if not surplus else ""))
        deposit = profile.monthly_deposit if need("monthly_deposit") else None
        existing_parts = _split(surplus, pct) if surplus else None
        monthly_parts = _split(deposit, pct) if deposit else None
        if deposit and safety.months_to_fill:
            reasons.append(f"ההפקדה החודשית מתחלקת לפי התמהיל אחרי {safety.months_to_fill} חודשים של השלמת קרן החירום.")
        capital = CapitalSection(
            equity_percent=eq, liquid_surplus=surplus, monthly_deposit=deposit,
            allocation=[AllocationLine(asset_class=k, percent=pct[k],
                                       existing_amount=existing_parts[k] if existing_parts else None,
                                       monthly_amount=monthly_parts[k] if monthly_parts else None)
                        for k in ASSET_CLASSES])

        # חוק 7: מסלול פנסיה והשתלמות לפי אחוז המניות מהטבלה, בלי תקרת גיל
        track = pension_track(profile.age, table_pct)
        pension = PensionSection(pension_track=track, study_fund_track=track)
        if profile.age < PENSION_ALL_EQUITY_UNDER_AGE:
            reasons.append(f"פנסיה והשתלמות: בגיל {profile.age}, מתחת ל-{PENSION_ALL_EQUITY_UNDER_AGE}, "
                           f"מסלול {PENSION_ALL_EQUITY_LABEL} בשתיהן.")
        else:
            reasons.append(f"פנסיה והשתלמות: בגיל {profile.age} המסלול נקבע לפי {table_pct:.0f}% מניות מהטבלה "
                           f"(בלי תקרת גיל): {track}.")

    # --- הערה: ריכוז בנכסים אחרים (מידע בלבד) ---
    if profile.other_assets:
        known = [v for v in (profile.liquid_savings, profile.pension_balance, profile.study_fund_balance,
                             profile.other_assets) if v is not None]
        share = profile.other_assets / sum(known)
        if share >= OTHER_ASSETS_CONCENTRATION:
            notes.append(f'נדל"ן ונכסים אחרים הם {share:.0%} מהנכסים הידועים. זה ריכוז גבוה בנכס אחד. מידע בלבד.')
            reasons.append(f"ריכוז: {_money(profile.other_assets)} מתוך {_money(sum(known))} נכסים ידועים "
                           f"= {share:.0%} (הסף {OTHER_ASSETS_CONCENTRATION:.0%}).")

    has_safety = safety.emergency_target_months is not None or safety.debt_ratio is not None
    return Proposal(as_of=today, missing=missing, safety=safety if has_safety else None, capital=capital,
                    pension=pension, notes=notes, reasons=reasons)


# ---------- חלוקת ההפקדה החודשית (הדיווח החודשי) ----------
class MonthlyLine(BaseModel):
    asset_class: str
    amount: float


class MonthlyAllocation(BaseModel):
    as_of: date
    deposit: float
    emergency_amount: float = 0.0          # לכספית, להשלמת קרן החירום
    lines: list[MonthlyLine] | None = None  # השאר לפי התמהיל. None = לא חושב (חסרים נתונים)
    unallocated: float = 0.0                # מה שלא חולק כי חסר תמהיל
    missing: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def allocate_monthly(profile: InvestorProfile, deposit: float, today: date | None = None) -> MonthlyAllocation:
    """מחלק הפקדה חודשית: קודם משלימים חוסר בקרן החירום (לכספית), והשאר לפי התמהיל של build_proposal.
    הסכומים מעוגלים כך שהסכום הכולל שווה בדיוק להפקדה. אין מכירות."""
    today = today or date.today()
    if deposit is None or deposit <= 0:
        raise ValueError("סכום ההשקעה החודש חייב להיות חיובי")
    deposit = round(float(deposit), 2)
    missing: list[str] = []
    reasons: list[str] = []
    need = _needs(profile, missing)

    emergency = 0.0
    if need("monthly_expenses", "liquid_savings"):
        months, target, shortfall = _emergency(profile)
        reasons.append(_emergency_reason(profile, months, target))
        emergency = round(min(shortfall, deposit), 2)
        if emergency:
            reasons.append(f"חסרים {_money(shortfall)} בקרן החירום, ולכן {_money(emergency)} מההפקדה הולכים קודם לכספית.")
        else:
            reasons.append("קרן החירום מלאה, ולכן כל ההפקדה מתחלקת לפי התמהיל.")
    else:
        reasons.append("אי אפשר לבדוק את קרן החירום בלי הוצאות חודשיות וכסף נזיל, ולכן לא הופרש לה סכום.")

    rest = round(deposit - emergency, 2)
    lines, unallocated = None, 0.0
    if not _required_ok(profile, need, missing):
        unallocated = rest
        if rest:
            reasons.append(f"{_money(rest)} לא חולקו: חסרים גיל, רמת סיכון מאושרת או אופק.")
    elif rest:
        _, _, pct = _mix(profile, reasons)
        parts = _split(rest, pct)
        lines = [MonthlyLine(asset_class=k, amount=parts[k]) for k in ASSET_CLASSES]
        reasons.append(f"{_money(rest)} מתחלקים לפי התמהיל.")
    else:
        lines = []
    return MonthlyAllocation(as_of=today, deposit=deposit, emergency_amount=emergency, lines=lines,
                             unallocated=unallocated, missing=missing, reasons=reasons)


class MonthlyReport(BaseModel):
    """דיווח חודשי אחד. period, net ו-set_aside נשמרים גם בהיסטוריה."""
    period: str
    net: float
    pension_contributions: float = 0.0
    study_fund_contributions: float = 0.0
    set_aside: float
    free_to_spend: float
    total_saved_this_month: float
    allocation: MonthlyAllocation


def monthly_report(profile: InvestorProfile, net: float, pension: float | None, study_fund: float | None,
                   amount_mode: str, amount_value: float, today: date | None = None) -> MonthlyReport:
    """הדיווח החודשי: כמה מושקע החודש (סכום קבוע או אחוז מהנטו), ואיך הוא מתחלק (allocate_monthly).
    amount_mode הוא "fixed" (שקלים) או "percent" (25 = 25% מהנטו). אין מכירות."""
    today = today or date.today()
    if not net or net <= 0:
        raise ValueError("הזן כמה נכנס נטו החודש")
    if any(v is not None and v < 0 for v in (pension, study_fund)):
        raise ValueError("הפקדות לפנסיה ולהשתלמות לא יכולות להיות שליליות")
    if not amount_value or amount_value <= 0:
        raise ValueError("הזן כמה להשקיע החודש: סכום בשקלים או אחוז מהנטו")
    if amount_mode == "percent":
        if amount_value > 100:
            raise ValueError("אחוז ההשקעה לא יכול לעלות על 100%")
        deposit = round(net * amount_value / 100, 2)
    elif amount_mode == "fixed":
        deposit = round(float(amount_value), 2)
    else:
        raise ValueError(f"אופן חישוב לא מוכר: {amount_mode}")
    if deposit > net:
        raise ValueError("הסכום להשקעה גבוה מהנטו שנכנס החודש")
    allocation = allocate_monthly(profile, deposit, today)
    if amount_mode == "percent":
        allocation.reasons.insert(0, f"סכום להשקעה: {amount_value:g}% מנטו של {_money(net)} = {_money(deposit)}.")
    pension, study_fund = round(pension or 0, 2), round(study_fund or 0, 2)
    return MonthlyReport(period=today.strftime("%Y-%m"), net=round(net, 2), pension_contributions=pension,
                         study_fund_contributions=study_fund, set_aside=deposit,
                         free_to_spend=round(net - deposit, 2),
                         total_saved_this_month=round(deposit + pension + study_fund, 2), allocation=allocation)
