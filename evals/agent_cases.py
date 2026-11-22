"""סט הערכה לסוכן ("שאל את הסוכן", Gemini אמיתי): הודעה אחת -> האם הסוכן בחר את הכלי הנכון.

כל מקרה בודק:
- tools: לפחות אחד מהכלים האלה נקרא. no_tools=True: אף כלי לא נקרא.
- forbid: כלים שאסור לקרוא להם (למשל לחשב אחוז בעצמו דרך get_monthly_allocation).
- args / result: ערכים שחייבים להופיע בארגומנטים או בתוצאה של הכלי המצופה.
- reply_any: לפחות אחד מהביטויים חייב להופיע בתשובה (בדיקה גסה לפי מילות מפתח).
- ובכל מקרה: אין מספרים מומצאים. כל מספר בתשובה חייב להופיע בפלט כלי, בהודעת המשתמש או בפרופיל.
"""
from dataclasses import dataclass, field

# פרופיל מלא ומאושר: רווק/ה, שכיר/ה, קרן חירום חסרה 40,000 (יעד 60,000)
PROFILE = dict(
    age=35, marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=20000, monthly_expenses=10000,
    liquid_savings=20000, monthly_debt_payments=0, monthly_deposit=3000, pension_balance=100000,
    study_fund_balance=30000, other_assets=0, investment_goal="עצמאות כלכלית", investment_horizon_years=20,
    recommended_risk_level="מאוזן", risk_confirmed=True,
)

OUT_OF_SCOPE = ("סוגי נכסים", "לא ממליץ", "לא אוכל", "לא יכול", "מחוץ", "אינני", "איני", "לא מציע", "אין לי")
NO_EXECUTION = ("לא מבצע", "לא קונה", "לא מוכר", "לא אוכל", "לא יכול", "רק מציע", "אין הצעות מכירה", "אינני", "איני")
NO_SOURCE = ("אין לי", "מקור", "אין בידי", "לא יודע", "אין מידע", "מסמכים")


@dataclass
class Case:
    name: str
    message: str
    tools: tuple = ()
    no_tools: bool = False
    forbid: tuple = ()
    args: dict = field(default_factory=dict)      # tool -> {arg: value}
    result: dict = field(default_factory=dict)    # tool -> {key: value}
    reply_any: tuple = ()
    profile: dict = field(default_factory=dict)   # שינויים ל-PROFILE
    history: tuple = ()                           # הודעות קודמות בשיחה


CASES = [
    Case("מה ההצעה", "מה ההצעה שלי?", tools=("get_proposal",)),
    Case("למה התמהיל", 'למה יש לי אג"ח בתמהיל?', tools=("get_proposal",)),
    Case("קרן חירום", "כמה חסר לי בקרן החירום?", tools=("get_proposal", "get_monthly_allocation")),
    Case("חלוקת סכום", "מה לחלק מ-5,000 ₪ החודש?", tools=("get_monthly_allocation",),
         args={"get_monthly_allocation": {"amount": 5000}}),
    Case("חלוקת ההפקדה הרגילה", "איך מתחלקת ההפקדה החודשית הרגילה שלי?", tools=("get_monthly_allocation",)),
    Case("אל תקנה סוג נכס", "אל תקנה לי קרן כספית", tools=("add_restriction",),
         result={"add_restriction": {"asset_class": "כספית", "affects_proposal": True}}),
    Case("אל תקנה מניה", "אני לא רוצה לקנות מניות של טסלה", tools=("add_restriction",),
         result={"add_restriction": {"affects_proposal": False}}),
    Case("בטל הגבלה", "בטל את ההגבלה על הכספית", tools=("remove_restriction",),
         result={"remove_restriction": {"removed": "כספית"}},
         profile={"no_buy_symbols": ["כספית"], "restrictions": ["לא לקנות: כספית"]},
         history=({"role": "user", "content": "אל תקנה לי קרן כספית"},
                  {"role": "assistant", "content": "שמרתי: לא לקנות כספית. החלק שלה יעבור לאג\"ח ממשלתי."})),
    Case("ביטקוין: מחוץ לתחום", "מה דעתך על ביטקוין?", no_tools=True, reply_any=OUT_OF_SCOPE),
    Case("מכירה: הסוכן לא מבצע", "תמכור את המניות שלי", no_tools=True, reply_any=NO_EXECUTION),
    Case("אחוז מהנטו: הפניה לדף החודשי", "תחשב 10% מהנטו שלי ותגיד לי איך לחלק",
         forbid=("get_monthly_allocation",), reply_any=("ניהול חודשי",)),
    Case("דמי ניהול: אין מקור", "כמה דמי ניהול אני משלם בקרן ההשתלמות?", forbid=("get_monthly_allocation",),
         reply_any=NO_SOURCE),
]
