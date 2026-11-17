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
 
    def is_complete(self) -> bool:
        """מוכן להרצת מנוע החישוב: יש גיל/שלב, אופק, ורמת סיכון שהמשתמש אישר"""
        return all([
            (self.age is not None or self.life_stage is not None),
            self.recommended_risk_level is not None,
            self.risk_confirmed,
            self.investment_horizon_years is not None,
        ])
 
 
LIST_FIELDS = ("relevant_vehicles", "restrictions")
 
 
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
        if key not in data or value is None:
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