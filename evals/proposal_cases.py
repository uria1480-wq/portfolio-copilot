"""סט הערכה להצעה ("קבל הצעה"): קוד בלבד, בלי LLM.

כל מקרה הוא פרופיל ריאליסטי עם מה שמצופה שהקוד יחשב. הערכים המצופים חושבו ביד מהחוקים
ב-design/mvp.md ובראש proposal.py, ולא מהרצת הקוד. כך הסט בודק את הקוד מול המפרט.

פרופיל הבסיס (BASE): בן/בת 35, רווק/ה, שכיר/ה, נטו 20,000, הוצאות 10,000, נזיל 60,000 (קרן חירום מלאה בדיוק),
בלי חובות, הפקדה 3,000, אופק 20 שנה, רמת סיכון מאוזן (מאושרת).

התמהיל נכתב כ-(ארה"ב, עולמי, ממשלתי, קונצרני, כספית) באחוזים.
החוקים בקצרה: מניות מטבלה (אופק עד 3/7/15/מעל, ורמת סיכון), תקרה 110 פחות הגיל. מהשאר: אג"ח 40% באופק עד 3 שנים,
אחרת 70%, חצי ממשלתי וחצי קונצרני, והיתר כספית. קרן חירום 3 חודשים לשכיר/ה עם בן/בת זוג מרוויח/ה, אחרת 6.
חוב: מעל 30% מהנטו מוסיף צעד. פנסיה: מתחת לגיל 40, 100% מנייתי. מעל, לפי אחוז המניות מהטבלה (80+ מנייתי, 40+ כללי).
"""
from dataclasses import dataclass, field

BASE = dict(
    age=35, marital_status="רווק", employment_status="שכיר/ה", monthly_net_income=20000, monthly_expenses=10000,
    liquid_savings=60000, monthly_debt_payments=0, monthly_deposit=3000, pension_balance=100000,
    study_fund_balance=30000, other_assets=0, investment_goal="פרישה", investment_horizon_years=20,
    recommended_risk_level="מאוזן", risk_confirmed=True,
)
BASE_MIX = (32.5, 32.5, 12.25, 12.25, 10.5)


@dataclass
class Case:
    name: str
    profile: dict                     # שינויים מול BASE. None בשדה = השדה חסר
    expect: dict = field(default_factory=dict)
    replace_base: bool = False        # True: הפרופיל הוא רק מה שב-profile (בלי BASE)


# מפתחות אפשריים ב-expect:
#   mix: (US, WLD, GOV, CORP, MM) | equity: אחוז מניות סופי | pension: מסלול
#   emergency_months, shortfall, months_to_fill, surplus | debt_ratio, reduce_debt (True/False)
#   no_capital: True (אין תמהיל) | no_safety: True | missing: שדות שחייבים להופיע ב-missing
#   reason / note / step: טקסט שחייב להופיע בנימוקים / בהערות / בצעדים
CASES = [
    # ---------- תמהיל לפי גיל, סיכון ואופק ----------
    Case("בסיס: 35, מאוזן, אופק 20", {}, dict(
        mix=BASE_MIX, equity=65, pension="100% מנייתי", emergency_months=6, shortfall=0, surplus=0)),
    Case("צעיר אגרסיבי: 25, אופק 30 (תקרת גיל 85)", dict(age=25, recommended_risk_level="אגרסיבי",
                                                       investment_horizon_years=30), dict(
        mix=(42.5, 42.5, 5.25, 5.25, 4.5), equity=85, pension="100% מנייתי", reason="תקרת גיל")),
    Case("נער 16, אגרסיבי, אופק 40", dict(age=16, employment_status="תלמיד/ה", monthly_net_income=0,
                                         monthly_expenses=500, liquid_savings=3000, monthly_deposit=300,
                                         recommended_risk_level="אגרסיבי", investment_horizon_years=40), dict(
        mix=(45, 45, 3.5, 3.5, 3), equity=90, pension="100% מנייתי", shortfall=0)),
    Case("שמרני 45, אופק 10", dict(age=45, recommended_risk_level="שמרני", investment_horizon_years=10), dict(
        mix=(15, 15, 24.5, 24.5, 21), equity=30, pension='אג"ח/שמרני')),
    Case("גבולי: אופק 3 בדיוק (אג\"ח 40%)", dict(investment_horizon_years=3), dict(
        mix=(5, 5, 18, 18, 54), equity=10)),
    Case("גבולי: אופק 4 (דלי 4-7)", dict(investment_horizon_years=4), dict(
        mix=(20, 20, 21, 21, 18), equity=40)),
    Case("אגרסיבי, אופק 7", dict(recommended_risk_level="אגרסיבי", investment_horizon_years=7), dict(
        mix=(30, 30, 14, 14, 12), equity=60)),
    Case("גבולי: גיל 70 אגרסיבי (תקרה 40, פנסיה מנייתי)", dict(age=70, recommended_risk_level="אגרסיבי"), dict(
        mix=(20, 20, 21, 21, 18), equity=40, pension="מנייתי", reason="תקרת גיל")),
    Case("גיל 70 מאוזן, אופק 10 (פנסיה כללי)", dict(age=70, investment_horizon_years=10), dict(
        mix=(20, 20, 21, 21, 18), equity=40, pension="כללי")),
    Case("גיל 85 שמרני, אופק 5", dict(age=85, recommended_risk_level="שמרני", investment_horizon_years=5), dict(
        mix=(10, 10, 28, 28, 24), equity=20, pension='אג"ח/שמרני')),

    # ---------- חוב ----------
    Case("גבולי: חוב 30% בדיוק (לא מעל הסף)", dict(monthly_debt_payments=6000), dict(
        debt_ratio=0.3, reduce_debt=False, mix=BASE_MIX)),
    Case("חוב 31%: צעד להקטנת חוב, התמהיל לא משתנה", dict(monthly_debt_payments=6200), dict(
        debt_ratio=0.31, reduce_debt=True, step="להקטין חוב", mix=BASE_MIX)),

    # ---------- קרן חירום ובן/בת זוג ----------
    Case("נשוי שכיר, בת זוג מרוויחה: 3 חודשים", dict(marital_status="נשוי", spouse_monthly_net_income=12000,
                                                   liquid_savings=20000), dict(
        emergency_months=3, shortfall=10000, months_to_fill=4, surplus=0)),
    Case("נשוי, בן/בת זוג בלי הכנסה: 6 חודשים", dict(marital_status="נשוי", spouse_monthly_net_income=0,
                                                    liquid_savings=20000), dict(
        emergency_months=6, shortfall=40000, months_to_fill=14)),
    Case("ידועה בציבור עצמאית, בן זוג מרוויח: 6 חודשים", dict(marital_status="ידוע בציבור",
                                                           employment_status="עצמאי/ת",
                                                           spouse_monthly_net_income=12000), dict(
        emergency_months=6, shortfall=0)),
    Case("עודף נזיל מעל קרן החירום", dict(liquid_savings=90000), dict(shortfall=0, surplus=30000)),

    # ---------- פרופיל חסר ----------
    Case("פרופיל חסר: רק גיל", dict(age=30), dict(
        no_capital=True, no_safety=True,
        missing=["recommended_risk_level", "investment_horizon_years", "monthly_expenses", "liquid_savings"]),
        replace_base=True),
    Case("רמת סיכון לא אושרה", dict(risk_confirmed=False), dict(
        no_capital=True, missing=["risk_confirmed"], emergency_months=6)),

    # ---------- הגבלות "אל תקנה" (restrictions.py) ----------
    Case('אל תקנה אג"ח קונצרני: עובר לממשלתי', dict(no_buy_symbols=['אג"ח קונצרני']), dict(
        mix=(32.5, 32.5, 24.5, 0, 10.5), equity=65, reason='ביקשת לא לקנות אג"ח קונצרני')),
    Case("אל תקנה מניות (כל הקבוצה): עובר לכספית", dict(no_buy_symbols=["מניות"]), dict(
        mix=(0, 0, 12.25, 12.25, 75.5), equity=0, reason="ביקשת לא לקנות מניות (")),
    Case('אל תקנה אג"ח (כל הקבוצה): עובר לכספית', dict(no_buy_symbols=["אגרות חוב"]), dict(
        mix=(32.5, 32.5, 0, 0, 35), equity=65)),
    Case("אל תקנה קרן כספית: התמהיל וקרן החירום עוברים לממשלתי", dict(no_buy_symbols=["קרן כספית"],
                                                                 liquid_savings=40000), dict(
        mix=(32.5, 32.5, 22.75, 12.25, 0), shortfall=20000, step='אג"ח ממשלתי')),
    Case("אל תקנה S&P 500 (ניסוח): ארה\"ב עובר לעולמי", dict(no_buy_symbols=["S&P 500"]), dict(
        mix=(0, 65, 12.25, 12.25, 10.5), equity=65)),
    Case("אל תקנה TSLA: סמל, ההצעה לא משתנה", dict(no_buy_symbols=["TSLA"]), dict(mix=BASE_MIX, equity=65)),

    # ---------- הערות ----------
    Case('ריכוז בנדל"ן: 72% מהנכסים', dict(other_assets=500000), dict(note="ריכוז גבוה", mix=BASE_MIX)),
]
