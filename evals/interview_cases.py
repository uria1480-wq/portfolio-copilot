"""סט הערכה לראיון (Gemini אמיתי): תשובה חופשית אחת של משתמש -> אילו שדות התעדכנו בפרופיל.

כל מקרה: פרופיל שבו חסר רק השדה שנשאל, השאלה שהסוכן שאל, תשובת המשתמש, ומה מצופה אחרי התור.
המסלול זהה לאפליקציה: chat_step -> update_profile -> apply_profile_update (אימות בקוד).

expect:
  {"field": value}          השדה צריך להיות בדיוק הערך הזה
  {"field": UNKNOWN}        השדה נשאר ריק ונרשם ב-unknown_fields ("לא יודע")
  {"field": UNCHANGED}      השדה לא השתנה ולא סומן "לא יודע" (תשובה לא ברורה)
rejected_in_code: השדה חייב להגיע ל-update_profile ולהידחות שם (ב-rejected), לא רק להישאר ריק.
"""
from dataclasses import dataclass, field
from datetime import date

UNKNOWN = "<לא יודע>"
UNCHANGED = "<לא השתנה>"

# פרופיל מלא (רווק/ה, שכיר/ה). בכל מקרה מוחקים ממנו את השדה שנשאל
FULL = dict(
    age=34, marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=18000, monthly_expenses=9000,
    monthly_deposit=2500, liquid_savings=40000, monthly_debt_payments=0, pension_balance=120000,
    study_fund_balance=35000, other_assets=0, investment_goal="עצמאות כלכלית", investment_horizon_years=15,
    recommended_risk_level="מאוזן", risk_confirmed=True,
)


@dataclass
class Case:
    name: str
    question: str               # מה הסוכן שאל בתור הקודם
    answer: str                 # תשובת המשתמש
    expect: dict
    clear: tuple = ()           # שדות שמוחקים מ-FULL (השדה שנשאל)
    profile: dict = field(default_factory=dict)  # שינויים נוספים לפרופיל ההתחלתי
    rejected_in_code: tuple = ()


def horizon_to(year: int, today: date) -> int:
    return year - today.year


def cases(today: date) -> list[Case]:
    return [
        Case("גיל במשפט", "בן/בת כמה את/ה?", "אני בן 34", {"age": 34}, clear=("age",)),
        Case("גיל במספר בלבד", "בן/בת כמה את/ה?", "52", {"age": 52}, clear=("age",)),
        Case("גיל 150 נדחה בקוד", "בן/בת כמה את/ה?", "אני בן 150", {"age": UNCHANGED}, clear=("age",),
             rejected_in_code=("age",)),
        Case("מצב משפחתי: נשוי", "מה המצב המשפחתי שלך?", "נשוי", {"marital_status": "נשוי"},
             clear=("marital_status",)),
        Case("מצב משפחתי בלשון נקבה", "מה המצב המשפחתי שלך?", "אני רווקה", {"marital_status": "רווק"},
             clear=("marital_status",)),
        Case("הכנסת בת זוג", "כמה בת הזוג שלך מרוויחה נטו בחודש?", "אשתי מרוויחה 9,000 נטו",
             {"spouse_monthly_net_income": 9000}, profile={"marital_status": "נשוי"}),
        Case("בן זוג לא עובד", "כמה בן הזוג שלך מרוויח נטו בחודש?", "בעלי לא עובד כרגע",
             {"spouse_monthly_net_income": 0}, profile={"marital_status": "נשוי"}),
        Case("מצב תעסוקתי חופשי", "מה המצב התעסוקתי שלך?", "אני שכיר בהייטק", {"employment_status": "שכיר/ה"},
             clear=("employment_status",)),
        Case("נטו בניסוח חופשי", "כמה נכנס לך נטו בחודש?", "בערך 18 אלף נטו", {"monthly_net_income": 18000},
             clear=("monthly_net_income",)),
        Case("אין חובות", "יש לך החזרי הלוואות או משכנתא?", "אין לי חובות", {"monthly_debt_payments": 0},
             clear=("monthly_debt_payments",)),
        Case("לא יודע (פנסיה)", "כמה יש לך בקרן הפנסיה?", "לא יודע כמה יש לי בפנסיה",
             {"pension_balance": UNKNOWN}, clear=("pension_balance",)),
        Case("כסף נזיל", "כמה כסף נזיל יש לך בבנק?", 'יש לי 50 אלף בעו"ש', {"liquid_savings": 50000},
             clear=("liquid_savings",)),
        Case("שנת יעד -> אופק בקוד", "לכמה זמן את/ה חוסך/ת?", "אני רוצה לחסוך עד 2040",
             {"investment_horizon_years": horizon_to(2040, today)}, clear=("investment_horizon_years",)),
        Case("אופק בשנים", "לכמה זמן את/ה חוסך/ת?", "בערך 10 שנים", {"investment_horizon_years": 10},
             clear=("investment_horizon_years",)),
        Case("תשובה לא ברורה", "כמה את/ה מוציא/ה בחודש?", "אממ... תלוי", {"monthly_expenses": UNCHANGED},
             clear=("monthly_expenses",)),
        Case("אישור רמת סיכון", "אני מציע רמת סיכון מאוזנת. זה מתאים לך?", "כן, מתאים לי",
             {"risk_confirmed": True}, profile={"risk_confirmed": False}),
    ]
