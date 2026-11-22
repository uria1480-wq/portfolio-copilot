from datetime import date
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, field_validator

def format_money(x: float) -> str:
    """סכום בשקלים לתצוגה, בלי אגורות: ₪12,345. הפונקציה היחידה לעיצוב כסף (הצעה, תמונת מצב, ממשק)."""
    return f"₪{x:,.0f}"


LEGACY_NO_SELL_PREFIX = "לא למכור: "  # הגבלות מגרסה קודמת ("לא מוכר"), שכבר אין להן משמעות
 
 
class InvestorProfile(BaseModel):
    """פרופיל משקיע הוליסטי המותאם לכל שלב בחיים"""
 
    # פרטים אישיים ושלב בחיים
    age: Optional[int] = Field(default=None, ge=0, le=120, description="גיל המשקיע")
    life_stage: Optional[str] = Field(
        default=None,
        description="שלב בחיים: נוער / סטודנט / משפחה צעירה / לקראת פרישה / פנסיונר",
    )
 
    # היקף ותזרים
    initial_amount: Optional[float] = Field(default=None, description="סכום ראשוני להשקעה (אם צוין)")
    monthly_deposit: Optional[float] = Field(default=None, description="הפקדה חודשית מתוכננת (אם צוינה)")
    needs_cashflow: Optional[bool] = Field(
        default=None,
        description="האם זקוק למשיכת קצבה/תזרים חודשי מהתיק (נפוץ בגיל פרישה) או רק צבירה",
    )
 
    # יעדים ומכשירים רלוונטיים
    investment_goal: Optional[str] = Field(
        default=None,
        description="מטרת ההשקעה העיקרית (עצמאות כלכלית, דירה, פנסיה, בר מצווה וכו')",
    )
    relevant_vehicles: List[str] = Field(
        default_factory=list,
        description="מכשירים שנבחנו: פנסיה, קופת גמל להשקעה, קרן השתלמות, תיק מסחר עצמאי, קרן כספית",
    )
 
    # ניתוח סיכון והמלצות
    recommended_risk_level: Optional[Literal["שמרני", "מאוזן", "אגרסיבי"]] = Field(
        default=None, description="רמת הסיכון שהסוכן מציע בהתאם למצב האישי (הצעה, עד לאישור המשתמש)"
    )
    risk_confirmed: bool = Field(
        default=False, description="האם המשתמש אישר במפורש את רמת הסיכון (או בחר אחרת בעצמו)"
    )
    investment_horizon_years: Optional[int] = Field(default=None, description="אופק ההשקעה בשנים")
    agent_reasoning: Optional[str] = Field(
        default=None, description="הסבר קצר של הסוכן מדוע רמת הסיכון והמכשירים האלו מתאימים"
    )
    restrictions: List[str] = Field(
        default_factory=list, description="מגבלות אישיות (מה לא לקנות, חרמות וכו')"
    )
    no_buy_symbols: List[str] = Field(
        default_factory=list, description="מה שהמשתמש אמר שלא יקנה (מניה, קרן או סוג נכס). נשמר דרך add_restriction"
    )

    # תמונת המצב הפיננסית מהראיון (תרחיש 2). סכומים בשקלים, לא שליליים.
    marital_status: Optional[str] = Field(default=None, description="מצב משפחתי")
    spouse_monthly_net_income: Optional[float] = Field(
        default=None, ge=0, description="הכנסה נטו חודשית של בן/בת הזוג. נדרשת רק לנשוי או ידוע בציבור"
    )
    employment_status: Optional[str] = Field(default=None, description="מצב תעסוקתי")
    monthly_net_income: Optional[float] = Field(default=None, ge=0, description="הכנסה נטו חודשית")
    monthly_expenses: Optional[float] = Field(default=None, ge=0, description="הוצאות חודשיות")
    liquid_savings: Optional[float] = Field(default=None, ge=0, description="כסף נזיל וחסכונות בבנק")
    monthly_debt_payments: Optional[float] = Field(default=None, ge=0, description="החזרי חובות בחודש")
    pension_balance: Optional[float] = Field(default=None, ge=0, description="יתרה בקרן הפנסיה")
    study_fund_balance: Optional[float] = Field(default=None, ge=0, description="יתרה בקרן ההשתלמות")
    other_assets: Optional[float] = Field(default=None, ge=0, description="נכסים אחרים")
    unknown_fields: List[str] = Field(
        default_factory=list, description="שדות שהמשתמש אמר שהוא לא יודע. לא נשאלים שוב"
    )

    @field_validator("restrictions")
    @classmethod
    def _drop_legacy_no_sell(cls, value: List[str]) -> List[str]:
        """פרופיל ישן: מוחק את ההגבלות "לא למכור: X" מהגרסה שבה היו הצעות מכירה. שאר המגבלות נשארות."""
        return [r for r in value if not str(r).startswith(LEGACY_NO_SELL_PREFIX)]

    def is_complete(self) -> bool:
        """מוכן להרצת מנוע החישוב: יש גיל/שלב, אופק, ורמת סיכון שהמשתמש אישר"""
        return all([
            (self.age is not None or self.life_stage is not None),
            self.recommended_risk_level is not None,
            self.risk_confirmed,
            self.investment_horizon_years is not None,
        ])

    def is_partnered(self) -> bool:
        """נשוי או ידוע בציבור. רק אז נשאלת הכנסת בן/בת הזוג ומוצגים שדות בן/בת הזוג בדיווח החודשי."""
        return self.marital_status in PARTNERED_STATUSES

    def missing_fields(self) -> list[str]:
        """מה עוד חסר כדי שהראיון יהיה מלא, בסדר קבוע שבו שואלים (שאלה אחת בכל פעם).
        שדה נחשב נענה אם יש לו ערך, או שהמשתמש אמר שהוא לא יודע (unknown_fields)."""
        missing = []
        if self.age is None and self.life_stage is None:
            missing.append("age")
        for field in INTERVIEW_FIELDS:
            if field == "spouse_monthly_net_income" and not self.is_partnered():
                continue
            if getattr(self, field) is None and field not in self.unknown_fields:
                missing.append(field)
        if self.recommended_risk_level is None:
            missing.append("recommended_risk_level")
        elif not self.risk_confirmed:
            missing.append("risk_confirmed")
        return missing


LIFE_STAGES = ("נוער", "סטודנט", "משפחה צעירה", "לקראת פרישה", "פנסיונר")
RISK_LEVELS = ("שמרני", "מאוזן", "אגרסיבי")
EMPLOYMENT_OPTIONS = ("שכיר/ה", "עצמאי/ת", "לא עובד/ת", "סטודנט/ית", "חייל/ת", "פנסיונר/ית", "תלמיד/ה")
MARITAL_OPTIONS = ("רווק", "נשוי", "ידוע בציבור", "גרוש", "אלמן")
PARTNERED_STATUSES = ("נשוי", "ידוע בציבור")
AMOUNT_FIELDS = ("spouse_monthly_net_income", "monthly_net_income", "monthly_expenses", "liquid_savings",
                 "monthly_debt_payments", "pension_balance", "study_fund_balance", "other_assets")

# סדר השאלות בראיון אחרי הגיל ולפני רמת הסיכון (תרחיש 2 ב-design/mvp.md)
INTERVIEW_FIELDS = ("marital_status", "spouse_monthly_net_income", "employment_status", "monthly_net_income", "monthly_expenses", "monthly_deposit",
                    "liquid_savings", "monthly_debt_payments", "pension_balance", "study_fund_balance",
                    "other_assets", "investment_goal", "investment_horizon_years")

# על אילו שדות אפשר לענות "לא יודע" ועל אילו "אין"
UNKNOWN_ALLOWED = ("employment_status", *AMOUNT_FIELDS, "investment_goal")
NONE_ALLOWED = (*AMOUNT_FIELDS, "investment_goal")
GOAL_NONE_TEXT = "אין יעד מוגדר"

# "לא יודע" מתקבל רק כשהמשתמש אמר זאת במפורש. בסט ההערכה המודל סימן "לא יודע" על "אממ... תלוי",
# ושיפור הפרומפט לא עזר, ולכן הקוד בודק את הודעת המשתמש עצמה.
EXPLICIT_UNKNOWN_PHRASES = ("לא יודע", "לא יודעת", "לא יודעים", "לא ידוע", "אין לי מושג", "אין מושג", "אין לי תשובה",
                            "אין לי מידע", "לא זוכר", "לא זוכרת", "אין לי דרך לדעת")
UNKNOWN_NOT_SAID = ("המשתמש לא אמר במפורש שהוא לא יודע, ולכן השדה לא סומן 'לא יודע'. "
                    "שאל שוב על השדה בניסוח פשוט, ואפשר לבקש הערכה גסה")


def said_unknown(user_message: str | None) -> bool:
    """האם בהודעה יש ניסוח מפורש של "לא יודע". None (אין הודעה, למשל קריאה ישירה מבדיקה): לא בודקים."""
    if user_message is None:
        return True
    text = " ".join(str(user_message).split())
    return any(phrase in text for phrase in EXPLICIT_UNKNOWN_PHRASES)


def _number(value, low=None, high=None, integer=False):
    """ממיר ערך למספר ובודק טווח. מחזיר (ערך, None) או (None, סיבת דחייה)."""
    if isinstance(value, bool):
        return None, "צריך להיות מספר"
    try:
        num = float(str(value).replace(",", "").strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None, "צריך להיות מספר"
    if num != num or num in (float("inf"), float("-inf")):
        return None, "צריך להיות מספר"
    if integer:
        if num != int(num):
            return None, "צריך להיות מספר שלם"
        num = int(num)
    if low is not None and num < low:
        return None, f"צריך להיות לפחות {low}"
    if high is not None and num > high:
        return None, f"צריך להיות לכל היותר {high}"
    return num, None


def _text(value):
    if not isinstance(value, str) or not value.strip():
        return None, "צריך להיות טקסט לא ריק"
    return value.strip(), None


def _choice(options):
    def check(value):
        if value not in options:
            return None, f"ערך לא חוקי. אפשרויות: {' / '.join(options)}"
        return value, None
    return check


def _bool(value):
    if not isinstance(value, bool):
        return None, "צריך להיות true או false"
    return value, None


PROFILE_VALIDATORS = {
    "age": lambda v: _number(v, 0, 120, integer=True),
    "life_stage": _choice(LIFE_STAGES),
    "initial_amount": lambda v: _number(v, 0),
    "monthly_deposit": lambda v: _number(v, 0),
    "needs_cashflow": _bool,
    "investment_goal": _text,
    "investment_horizon_years": lambda v: _number(v, 1, 80, integer=True),
    "recommended_risk_level": _choice(RISK_LEVELS),
    "risk_confirmed": _bool,
    "agent_reasoning": _text,
    "employment_status": _choice(EMPLOYMENT_OPTIONS),
    "marital_status": _choice(MARITAL_OPTIONS),
    **{field: (lambda v: _number(v, 0)) for field in AMOUNT_FIELDS},
}


def _field_list(value):
    """רשימת שמות שדות מהמודל. מחזיר (רשימה, None) או (None, סיבה)."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        return None, "צריך להיות רשימה של שמות שדות"
    return list(dict.fromkeys(x.strip() for x in value if x.strip())), None


def horizon_from_target_year(value, today: date) -> tuple[int | None, str | None]:
    """שנת יעד -> אופק בשנים, מחושב בקוד מול התאריך של היום. מחזיר (אופק, None) או (None, סיבת דחייה)."""
    year, reason = _number(value, integer=True)
    if reason:
        return None, reason
    horizon = year - today.year
    if horizon < 1:
        return None, f"שנת היעד {year} לא בעתיד (השנה {today.year}). צריך שנה מ-{today.year + 1} והלאה"
    if horizon > 80:
        return None, f"שנת היעד {year} רחוקה מדי: אופק של {horizon} שנים, והמקסימום 80"
    return horizon, None


def apply_profile_update(current: InvestorProfile, patch: dict, today: date | None = None,
                         user_message: str | None = None) -> tuple[InvestorProfile, dict, dict]:
    """מעדכן פרופיל מערכים שהמודל חילץ, אחרי בדיקה בקוד של כל שדה בנפרד.

    מחזיר (פרופיל חדש, מה התקבל, מה נדחה וסיבה). ערך null מדולג. שדה לא מוכר נדחה.
    שינוי רמת סיכון מאפס את האישור, ואישור סיכון נדחה כשאין רמת סיכון.

    target_year: שנת יעד. הקוד מחשב investment_horizon_years = target_year - השנה של today
    (ברירת מחדל: date.today()). target_year עצמו לא נשמר בפרופיל.

    unknown_fields: שדות שהמשתמש אמר שהוא לא יודע. הערך נשאר ריק והשדה לא נשאל שוב.
    none_fields: שדות שהמשתמש אמר שאין לו. הקוד רושם 0 לסכום, ו"אין יעד מוגדר" ליעד.
    שדה שמגיע באותה קריאה גם עם ערך וגם כ"לא יודע"/"אין" נדחה כולו.
    """
    patch = patch if isinstance(patch, dict) else {}
    data = current.model_dump()
    accepted, rejected = {}, {}

    markers = {}
    for key in ("unknown_fields", "none_fields"):
        if patch.get(key) is None:
            markers[key] = []
            continue
        names, reason = _field_list(patch[key])
        if reason:
            rejected[key] = reason
        markers[key] = names or []
    if markers["unknown_fields"] and not said_unknown(user_message):
        for name in markers["unknown_fields"]:
            rejected[name] = UNKNOWN_NOT_SAID
        markers["unknown_fields"] = []
    conflicts = ({k for k in markers["unknown_fields"] + markers["none_fields"] if patch.get(k) is not None}
                 | (set(markers["unknown_fields"]) & set(markers["none_fields"])))
    for name in conflicts:
        rejected[name] = "התקבלו לאותו שדה גם ערך וגם 'לא יודע' או 'אין'. שאל שוב"

    for key, value in patch.items():
        if value is None or key in ("risk_confirmed", "unknown_fields", "none_fields") or key in conflicts:
            continue
        if key == "relevant_vehicles":
            items = [value] if isinstance(value, str) else value
            if not isinstance(items, list):
                rejected[key] = "צריך להיות רשימה"
                continue
            items = [str(x).strip() for x in items if str(x).strip()]
            data[key] = list(dict.fromkeys([*data[key], *items]))
            accepted[key] = data[key]
            continue
        if key == "target_year":
            ref = today or date.today()
            horizon, reason = horizon_from_target_year(value, ref)
            if reason:
                rejected[key] = reason
                continue
            data["investment_horizon_years"] = horizon
            accepted[key] = ref.year + horizon
            accepted["investment_horizon_years"] = horizon
            continue
        validator = PROFILE_VALIDATORS.get(key)
        if validator is None:
            rejected[key] = ("מגבלות נשמרות דרך add_restriction" if key in ("restrictions", "no_buy_symbols")
                             else "שדה לא מוכר")
            continue
        clean, reason = validator(value)
        if reason:
            rejected[key] = reason
            continue
        data[key] = clean
        accepted[key] = clean
        if key in data["unknown_fields"]:  # ערך אמיתי מחליף "לא יודע"
            data["unknown_fields"] = [f for f in data["unknown_fields"] if f != key]

    for name in markers["none_fields"]:
        if name in conflicts:
            continue
        if name not in NONE_ALLOWED:
            rejected[name] = "אי אפשר לענות 'אין' על השדה הזה"
            continue
        data[name] = GOAL_NONE_TEXT if name == "investment_goal" else 0.0
        data["unknown_fields"] = [f for f in data["unknown_fields"] if f != name]
        accepted[name] = data[name]

    for name in markers["unknown_fields"]:
        if name in conflicts:
            continue
        if name not in UNKNOWN_ALLOWED:
            rejected[name] = "אי אפשר לענות 'לא יודע' על השדה הזה. צריך ערך"
            continue
        if data[name] is not None:
            rejected[name] = "כבר יש לשדה ערך. אם הוא השתנה, שלח את הערך החדש"
            continue
        if name not in data["unknown_fields"]:
            data["unknown_fields"] = [*data["unknown_fields"], name]
        accepted[name] = "unknown"

    if data["recommended_risk_level"] != current.recommended_risk_level:
        data["risk_confirmed"] = False

    if patch.get("risk_confirmed") is not None:
        clean, reason = _bool(patch["risk_confirmed"])
        if reason:
            rejected["risk_confirmed"] = reason
        elif clean and data["recommended_risk_level"] is None:
            rejected["risk_confirmed"] = "אין עדיין רמת סיכון לאשר"
        else:
            data["risk_confirmed"] = clean
            accepted["risk_confirmed"] = clean

    return InvestorProfile(**data), accepted, rejected
