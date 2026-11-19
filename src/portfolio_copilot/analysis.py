"""ניתוח והדרכה: מודל שפה מסביר ומציע תוכנית, והקוד מגביל אותה לנתונים של המשתמש.
אם המודל נכשל, מוצגת תוכנית בסיסית שנגזרת מהתשובות בקוד."""
import json
import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from portfolio_copilot.intake import IntakeAnswers
from portfolio_copilot.plan import Bucket, SavingsPlan

LEVELS = ("שמרני", "מאוזן", "אגרסיבי")


class Step(BaseModel):
    title: str
    why: str = ""


class Guidance(BaseModel):
    summary: str = ""
    risk_level: Optional[Literal["שמרני", "מאוזן", "אגרסיבי"]] = None
    risk_reasoning: str = ""
    steps: list[Step] = Field(default_factory=list)
    plan: Optional[SavingsPlan] = None
    source: Literal["llm", "fallback"] = "llm"
    missing: list[str] = Field(default_factory=list)  # הפערים מתמונת המצב, נקבעים בקוד ולא על ידי המודל


def _cash_share(months: float | None) -> float:
    """כמה מההפרשה נשאר נזיל, לפי כמה חודשי הוצאות מכוסים היום."""
    if months is None:
        return 0.3
    return 0.6 if months < 3 else 0.2 if months < 6 else 0.0


def _buckets(cash: float) -> list[Bucket]:
    if cash <= 0:
        return [Bucket(name="השקעות", kind="invest", share=1.0)]
    return [Bucket(name="כסף נזיל / קרן חירום", kind="cash", share=cash),
            Bucket(name="השקעות", kind="invest", share=1 - cash)]


def clamp_plan(plan: SavingsPlan, answers: IntakeAnswers) -> SavingsPlan:
    """התוכנית לא יכולה להפריש יותר ממה שהמשתמש אמר שהוא יכול."""
    cap, income = answers.can_save_monthly, answers.monthly_net_income
    if plan.savings_value is None or cap is None:
        return plan
    if plan.savings_mode == "fixed" and plan.savings_value > cap:
        plan.savings_value = cap
    elif plan.savings_mode == "percent" and income and plan.savings_value * income > cap:
        plan.savings_value = round(cap / income, 4)
    return plan


def default_guidance(answers: IntakeAnswers, picture: dict, suggested_risk: str, reasons: list[str] | None = None) -> Guidance:
    can_save = answers.can_save_monthly  # None נשאר None: לא מנחשים 0
    income, months = picture.get("monthly_net_income"), picture.get("emergency_months")
    steps = []
    if months is not None and months < 3:
        steps.append(Step(title="להשלים קרן חירום", why=f"הכסף הנזיל מכסה כ-{months:.1f} חודשי הוצאות, והיעד הוא לפחות 3."))
    for gap in picture.get("gaps", []):
        if "פנסיה" in gap or "השתלמות" in gap:
            steps.append(Step(title="להשלים את תמונת החיסכון הפנסיוני", why=gap + ". בלי זה אי אפשר לדעת כמה כבר צבור."))
    if can_save is None:
        steps.append(Step(title="להשלים כמה אפשר להפריש בחודש", why="בלי הסכום הזה אי אפשר לבנות תוכנית הפרשה."))
    elif can_save > 0:
        steps.append(Step(title="להפריש בכל חודש", why=f"הפרשה של {can_save:,.0f} ₪ בחודש, כפי שציינת שאפשר."))
    if can_save is None:
        summary = "חסר כמה אפשר להפריש בחודש, ולכן עדיין לא נבנתה תוכנית. ראה מה חסר למטה."
    elif income and can_save:
        summary = f"בהכנסה נטו של {income:,.0f} ₪ אפשר להפריש {can_save:,.0f} ₪ בחודש ({can_save / income:.0%} מהנטו)."
    else:
        summary = "נבנתה תוכנית בסיסית מהתשובות שלך."
    plan = None
    if can_save is not None and can_save > 0:
        plan = SavingsPlan(
            monthly_net_income=income, savings_mode="fixed", savings_value=can_save,
            buckets=_buckets(_cash_share(months)),
            rationale="תוכנית בסיסית מהתשובות שלך: ההפרשה היא הסכום שאמרת שאפשר, והחלוקה לפי כמה חודשי הוצאות מכוסים בכסף הנזיל.",
        )
    return Guidance(summary=summary, risk_level=suggested_risk if suggested_risk in LEVELS else None,
                    risk_reasoning="; ".join(reasons or []), steps=steps, plan=plan, source="fallback",
                    missing=list(picture.get("gaps", [])))


GUIDANCE_PROMPT = """אתה אנליסט תכנון פיננסי בפרויקט אקדמי בקורס מבוא לבינה מלאכותית. אתה לא יועץ מורשה.
קיבלת JSON עם תשובות ראיון של משתמש ותמונת מצב פיננסית מחושבת. כתוב הדרכה אישית בעברית פשוטה.
החזר אך ורק אובייקט JSON תקין (ללא מרקדאון) במבנה:
{
  "summary": "שתי שלוש שורות על המצב של האדם",
  "risk_level": "שמרני / מאוזן / אגרסיבי",
  "risk_reasoning": "למה רמת הסיכון הזו",
  "steps": [{"title": "צעד קצר", "why": "למה הוא חשוב לאדם הזה"}],
  "plan": {
    "savings_mode": "fixed או percent",
    "savings_value": מספר (שקלים, או שבר מהנטו),
    "buckets": [{"name": "שם", "kind": "cash או invest", "share": מספר בין 0 ל-1}],
    "rationale": "למה התוכנית מתאימה"
  }
}
כללים:
- השתמש רק במספרים שבקלט. אל תמציא ואל תחשב נתונים חדשים. אם חסר נתון, אמור שחסר.
- 3 עד 6 צעדים, לפי סדר חשיבות לאדם הזה. התאם לגיל, להכנסה, למטרות ולפערי המידע.
- ההפרשה לא תעלה על can_save_monthly. סכום ה-share צריך להיות 1.
- חלוקה בין cash (קרן חירום, מטרה קרובה) ל-invest לפי emergency_months וליעדים של האדם.
- אל תמליץ על קרנות או מוצרים ספציפיים, ואל תבטיח תשואה.
- הצג את הכל כהצעה שהמשתמש יחליט עליה."""


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    return json.loads(match.group(0) if match else text, strict=False)


def _build(data: dict, answers: IntakeAnswers, picture: dict, fallback: Guidance) -> Guidance:
    plan = None
    plan_data = data.get("plan")
    if isinstance(plan_data, dict) and plan_data.get("savings_value"):
        plan = SavingsPlan.model_validate({**plan_data, "confirmed": False,
                                           "monthly_net_income": picture.get("monthly_net_income")})
        plan = clamp_plan(plan, answers)
    steps = [Step(title=str(s["title"]), why=str(s.get("why", ""))) for s in data.get("steps", [])
             if isinstance(s, dict) and s.get("title")][:8]
    guidance = Guidance(
        summary=str(data.get("summary") or ""),
        risk_level=data.get("risk_level") if data.get("risk_level") in LEVELS else None,
        risk_reasoning=str(data.get("risk_reasoning") or ""),
        steps=steps,
        plan=plan or fallback.plan,
        source="llm",
    )
    if not guidance.summary and not guidance.steps:
        raise ValueError("תשובת המודל ריקה")
    return guidance


def analyze(answers: IntakeAnswers, picture: dict, suggested_risk: str, reasons: list[str], client, model: str,
            today: date | None = None) -> Guidance:
    """today נכנס להנחיה כדי שהמודל לא יניח שנה אחרת (ברירת מחדל: date.today())."""
    today = today or date.today()
    fallback = default_guidance(answers, picture, suggested_risk, reasons)
    payload = {"answers": answers.model_dump(), "picture": {k: picture[k] for k in
               ("items", "total", "monthly_net_income", "can_save_monthly", "savings_rate", "emergency_months", "gaps")},
               "suggested_risk_by_questionnaire": suggested_risk, "reasons": reasons}
    try:
        response = client.chat.completions.create(
            model=model, temperature=0.3,
            messages=[{"role": "system", "content": f"{GUIDANCE_PROMPT}\nהתאריך היום: {today.isoformat()}"},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        guidance = _build(_parse_json(response.choices[0].message.content), answers, picture, fallback)
        if guidance.risk_level is None:
            guidance.risk_level = fallback.risk_level
        guidance.missing = list(picture.get("gaps", []))
        return guidance
    except Exception as e:
        print("[analysis] הניתוח האוטומטי נכשל, מוצגת תוכנית בסיסית:", repr(e)[:300])
        return fallback