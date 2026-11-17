from typing import Literal, Optional, List
from pydantic import BaseModel, Field, ValidationError
 
 
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
    max_single_asset_weight: Optional[float] = Field(
        default=0.20, ge=0.05, le=1.0, description="תקרת פיזור לנכס בודד (ברירת מחדל 20%)"
    )
    agent_reasoning: Optional[str] = Field(
        default=None, description="הסבר קצר של הסוכן מדוע רמת הסיכון והמכשירים האלו מתאימים"
    )
    restrictions: List[str] = Field(
        default_factory=list, description="מגבלות אישיות (נכסים לא למכירה, חרמות וכו')"
    )
    no_sell_symbols: List[str] = Field(
        default_factory=list, description="סימולים שהמשתמש אמר שלא ימכור. נאכף בקוד בכל חישוב מכירה"
    )

    def is_complete(self) -> bool:
        """מוכן להרצת מנוע החישוב: יש גיל/שלב, אופק, ורמת סיכון שהמשתמש אישר"""
        return all([
            (self.age is not None or self.life_stage is not None),
            self.recommended_risk_level is not None,
            self.risk_confirmed,
            self.investment_horizon_years is not None,
        ])

    def missing_fields(self) -> list[str]:
        """מה עוד חסר כדי שהפרופיל יהיה מלא, בסדר שבו כדאי לשאול (שאלה אחת בכל פעם)."""
        missing = []
        if self.age is None and self.life_stage is None:
            missing.append("age")
        if self.investment_horizon_years is None:
            missing.append("investment_horizon_years")
        if self.recommended_risk_level is None:
            missing.append("recommended_risk_level")
        elif not self.risk_confirmed:
            missing.append("risk_confirmed")
        if self.monthly_deposit is None:
            missing.append("monthly_deposit")
        return missing


LIST_FIELDS = ("relevant_vehicles", "restrictions")
# שדות שמשתנים רק דרך כלי ייעודי (add_restriction), ולא דרך ה-JSON החופשי של המודל
PROTECTED_FIELDS = ("no_sell_symbols",)

LIFE_STAGES = ("נוער", "סטודנט", "משפחה צעירה", "לקראת פרישה", "פנסיונר")
RISK_LEVELS = ("שמרני", "מאוזן", "אגרסיבי")


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
    "max_single_asset_weight": lambda v: _number(v, 0.05, 1.0),
    "agent_reasoning": _text,
}


def apply_profile_update(current: InvestorProfile, patch: dict) -> tuple[InvestorProfile, dict, dict]:
    """מעדכן פרופיל מערכים שהמודל חילץ, אחרי בדיקה בקוד של כל שדה בנפרד.

    מחזיר (פרופיל חדש, מה התקבל, מה נדחה וסיבה). ערך null מדולג. שדה לא מוכר נדחה.
    שינוי רמת סיכון מאפס את האישור, ואישור סיכון נדחה כשאין רמת סיכון.
    """
    patch = patch if isinstance(patch, dict) else {}
    data = current.model_dump()
    accepted, rejected = {}, {}

    for key, value in patch.items():
        if value is None or key == "risk_confirmed":
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
        validator = PROFILE_VALIDATORS.get(key)
        if validator is None:
            rejected[key] = ("מגבלות נשמרות דרך add_restriction" if key in ("restrictions", "no_sell_symbols")
                             else "שדה לא מוכר")
            continue
        clean, reason = validator(value)
        if reason:
            rejected[key] = reason
            continue
        data[key] = clean
        accepted[key] = clean

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
 
 
def merge_profile(current: InvestorProfile, patch: dict) -> InvestorProfile:
    """ממזג עדכון מהמודל לפרופיל הקיים בלי לאבד מידע.
 
    - שדה ריק (null) לא דורס ערך קיים.
    - רשימות (מגבלות, מכשירים) מתאחדות ולא מוחלפות.
    - ערך שלא עובר ולידציה (למשל "בינוני" כרמת סיכון) נזרק, והערך הקודם נשמר.
    - שינוי של רמת הסיכון מאפס את האישור, אלא אם המשתמש אישר באותו תור.
    """
    patch = patch if isinstance(patch, dict) else {}
    data = current.model_dump()
    old_risk = data["recommended_risk_level"]
 
    for key, value in patch.items():
        if key not in data or value is None or key in PROTECTED_FIELDS:
            continue
        if key in LIST_FIELDS:
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list):
                continue
            items = [str(x).strip() for x in value if str(x).strip()]
            data[key] = list(dict.fromkeys([*data[key], *items]))
        else:
            data[key] = value
 
    if data["recommended_risk_level"] != old_risk and patch.get("risk_confirmed") is not True:
        data["risk_confirmed"] = False
 
    for _ in range(len(data) + 1):
        try:
            return InvestorProfile(**data)
        except ValidationError as e:
            bad = {err["loc"][0] for err in e.errors() if err["loc"]}
            if not bad:
                break
            for field in bad:
                data[field] = getattr(current, field)
    return current