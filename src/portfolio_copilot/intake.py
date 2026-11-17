"""ראיון ההיכרות: השאלות, ניקוד סיכון ובניית פרופיל משקיע. הכל בקוד, בלי מודל שפה, כדי שיהיה יציב."""
import re
from typing import Optional

from pydantic import BaseModel, Field

from portfolio_copilot.schemas import InvestorProfile

STATUS_OPTIONS = ["תלמיד/ה", "חייל/ת", "סטודנט/ית", "שכיר/ה", "עצמאי/ת", "פנסיונר/ית"]
GOAL_OPTIONS = ["קרן חירום", "רכישת דירה", "פרישה", "חינוך ילדים", "הגדלת הון", "רכישה גדולה (רכב, שיפוץ)"]
HORIZON_OPTIONS = {"עד 3 שנים": 3, "3 עד 7 שנים": 5, "7 עד 15 שנים": 10, "יותר מ-15 שנים": 20}
REACTION_OPTIONS = {
    "אמכור הכל כדי לא להפסיד עוד": 0,
    "אמכור חלק": 1,
    "לא אעשה כלום ואחכה": 2,
    "אקנה עוד, זו הזדמנות": 3,
}
EXPERIENCE_OPTIONS = {"אין לי ניסיון": 0, "קצת ניסיון": 1, "מנוסה": 2}
MAX_WEIGHT_OPTIONS = {"עד 10%": 0.10, "עד 20%": 0.20, "עד 30%": 0.30, "עד 50%": 0.50}


class IntakeAnswers(BaseModel):
    age: Optional[int] = Field(default=None, ge=0, le=120)
    status: Optional[str] = None
    monthly_net_income: Optional[float] = Field(default=None, ge=0)
    monthly_expenses: Optional[float] = Field(default=None, ge=0)
    can_save_monthly: Optional[float] = Field(default=None, ge=0)
    liquid_savings: Optional[float] = Field(default=None, ge=0)
    monthly_debt_payments: Optional[float] = Field(default=None, ge=0)
    goals: list[str] = Field(default_factory=list)
    horizon_label: Optional[str] = None
    reaction_label: Optional[str] = None
    experience_label: Optional[str] = None
    max_weight_label: Optional[str] = None
    restrictions_text: str = ""
    # ערכים שמוזנים ידנית כשאין מסמך
    pension_value: Optional[float] = Field(default=None, ge=0)
    study_fund_value: Optional[float] = Field(default=None, ge=0)
    other_assets: Optional[float] = Field(default=None, ge=0)


REQUIRED = {
    "age": "גיל", "status": "מצב תעסוקתי", "monthly_net_income": "הכנסה נטו חודשית",
    "can_save_monthly": "כמה אפשר להפריש בחודש", "horizon_label": "אופק השקעה",
    "reaction_label": "תגובה לירידה בתיק", "experience_label": "ניסיון בהשקעות",
}


def missing_fields(a: IntakeAnswers) -> list[str]:
    """שמות השאלות החובה שעדיין לא נענו."""
    return [label for field, label in REQUIRED.items() if getattr(a, field) in (None, "")]


def risk_assessment(a: IntakeAnswers) -> tuple[str, list[str], int]:
    """רמת סיכון מוצעת, הסיבות לה והניקוד. זו הצעה, והמשתמש מאשר או משנה."""
    score, reasons = 0, []
    if a.reaction_label in REACTION_OPTIONS:
        score += REACTION_OPTIONS[a.reaction_label]
        reasons.append(f"תגובה לירידה בתיק: {a.reaction_label}")
    if a.experience_label in EXPERIENCE_OPTIONS:
        score += EXPERIENCE_OPTIONS[a.experience_label]
        reasons.append(f"ניסיון: {a.experience_label}")
    if a.horizon_label in HORIZON_OPTIONS:
        years = HORIZON_OPTIONS[a.horizon_label]
        score += {3: 0, 5: 1, 10: 2, 20: 3}[years]
        reasons.append(f"אופק השקעה: {a.horizon_label}")
    if a.age is not None and a.age >= 65:
        score -= 2
        reasons.append("גיל מתקדם: חשוב לשמור על הערך")
    elif a.age is not None and a.age >= 55:
        score -= 1
        reasons.append("קרוב לפרישה: עדיפות ליציבות")
    if a.monthly_expenses and a.liquid_savings is not None and a.liquid_savings < 3 * a.monthly_expenses:
        score -= 1
        reasons.append("הכסף הנזיל נמוך מ-3 חודשי הוצאות")
    level = "שמרני" if score <= 2 else "מאוזן" if score <= 5 else "אגרסיבי"
    return level, reasons, score


def parse_restrictions(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[\n,;]+", text or "") if p.strip()]


def derive_profile(a: IntakeAnswers) -> InvestorProfile:
    """פרופיל משקיע מתשובות הראיון. רמת הסיכון היא הצעה בלבד (risk_confirmed=False)."""
    level, reasons, _ = risk_assessment(a)
    if a.status == "פנסיונר/ית" or (a.age or 0) >= 67:
        stage = "פנסיונר"
    elif (a.age or 0) >= 55:
        stage = "לקראת פרישה"
    elif a.status == "תלמיד/ה" or (a.age is not None and a.age < 18):
        stage = "נוער"
    else:
        stage = a.status
    return InvestorProfile(
        age=a.age,
        life_stage=stage,
        monthly_deposit=a.can_save_monthly,
        needs_cashflow=(stage == "פנסיונר"),
        investment_goal=", ".join(a.goals) or None,
        investment_horizon_years=HORIZON_OPTIONS.get(a.horizon_label),
        max_single_asset_weight=MAX_WEIGHT_OPTIONS.get(a.max_weight_label, 0.20),
        recommended_risk_level=level,
        risk_confirmed=False,
        agent_reasoning="; ".join(reasons) or None,
        restrictions=parse_restrictions(a.restrictions_text),
    )