"""קריאת מסמכים פיננסיים שהמשתמש מעלה. כרגע: תלוש שכר בפורמט PDF.

השלבים:
1. חילוץ טקסט מה-PDF בקוד (pdfplumber), כולל תיקון עברית שיוצאת הפוכה.
2. הסתרת פרטים מזהים (ת"ז, חשבון בנק, תיקי ניכויים) לפני שהטקסט נשלח למודל.
3. ה-LLM ממפה את הטקסט לסכמה קבועה (Pydantic). זה החלק שקוד רגיל מתקשה בו,
   כי לכל תוכנת שכר (מיכפל, חילן, סינאל) יש פריסה אחרת.
4. בדיקות חשבון בקוד: ברוטו פחות ניכויי חובה = נטו, וכו'. אם משהו לא מסתדר,
   התוצאה מסומנת כדי שהסוכן יבקש מהמשתמש לאמת.
קובץ ה-PDF עצמו לא נשמר. נשמרים רק המספרים שחולצו.
"""
import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

FINAL_LETTERS = "םןץףך"
TOLERANCE = 1.0  # סטייה מותרת בשקלים, בגלל עיגולים בתלוש


# --- 1. חילוץ טקסט ---
def _looks_visual(text: str) -> bool:
    """האם העברית יצאה בסדר הפוך (סדר תצוגה). אות סופית בתחילת מילה מעידה על כך."""
    words = re.findall(r"[א-ת]{2,}", text)
    starts = sum(w[0] in FINAL_LETTERS for w in words)
    ends = sum(w[-1] in FINAL_LETTERS for w in words)
    return starts > ends


def fix_hebrew_order(text: str) -> str:
    if not _looks_visual(text):
        return text
    from bidi import get_display
    return "\n".join(get_display(line) for line in text.splitlines())


def pdf_to_text(path: str | Path) -> str:
    import pdfplumber  # יבוא מאוחר, כדי שהבדיקות לא ידרשו קובץ PDF

    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    if not text.strip():
        raise ValueError("לא נמצא טקסט בקובץ. ייתכן שזה מסמך סרוק (תמונה), וזה עדיין לא נתמך.")
    return fix_hebrew_order(text)


# --- 2. הסתרת פרטים מזהים ---
SENSITIVE_LABELS = r"(מספר זהות|ת\.ז\.?|חשבון|בנק|סניף|תיק ניכויים|מספר תאגיד|תיק בי''?ל)"


def redact(text: str) -> str:
    text = re.sub(rf"{SENSITIVE_LABELS}\s*:?\s*[\d/\-]{{3,}}", r"\1: [הוסתר]", text)
    text = re.sub(r"\b\d{8,}\b", "[הוסתר]", text)  # מספר ארוך שנשאר (ת"ז, חשבון)
    return text


# --- 3. סכמה וחילוץ בעזרת LLM ---
class Payslip(BaseModel):
    """שדות מתלוש שכר ישראלי. כל סכום בשקלים לחודש. null אם לא מופיע בתלוש."""

    period: Optional[str] = Field(default=None, description="חודש התלוש בפורמט YYYY-MM")
    employer: Optional[str] = Field(default=None, description="שם המעסיק")
    gross_pay: Optional[float] = Field(default=None, description='סה"כ תשלומים (ברוטו), בלי שווי למס')
    taxable_benefits: Optional[float] = Field(default=None, description="שווי למס (רכב, דירה וכו')")
    income_tax: Optional[float] = Field(default=None, description="מס הכנסה שנוכה")
    national_insurance: Optional[float] = Field(default=None, description="ביטוח לאומי (עובד)")
    health_tax: Optional[float] = Field(default=None, description="מס בריאות")
    pension_employee: Optional[float] = Field(default=None, description="הפרשת עובד לפנסיה/גמל")
    study_fund_employee: Optional[float] = Field(default=None, description="הפרשת עובד לקרן השתלמות")
    mandatory_deductions_total: Optional[float] = Field(default=None, description='סה"כ ניכויי חובה')
    net_pay: Optional[float] = Field(default=None, description="שכר נטו")
    voluntary_deductions_total: Optional[float] = Field(default=None, description='סה"כ ניכויי רשות')
    net_to_bank: Optional[float] = Field(default=None, description="לתשלום (מה שנכנס לבנק)")
    pension_employer: Optional[float] = Field(default=None, description="הפרשת מעסיק לתגמולים (גמל מעסיק)")
    severance_employer: Optional[float] = Field(default=None, description="הפרשת מעסיק לפיצויים")
    study_fund_employer: Optional[float] = Field(default=None, description="הפרשת מעסיק לקרן השתלמות")
    pension_fund: Optional[str] = Field(default=None, description="שם קרן הפנסיה/קופת הגמל")
    marginal_tax_rate: Optional[float] = Field(default=None, ge=0, le=0.5, description="מס שולי כשבר, 14% = 0.14")
    credit_points: Optional[float] = Field(default=None, description="סך נקודות זיכוי")

    @field_validator("*", mode="before")
    @classmethod
    def _clean_number(cls, v, info):
        """המודל לפעמים מחזיר '6,082.87' או '₪500'. ממירים למספר."""
        if isinstance(v, str) and cls.model_fields[info.field_name].annotation == Optional[float]:
            cleaned = re.sub(r"[₪,%\s]", "", v)
            return float(cleaned) if cleaned else None
        return v

    @field_validator("marginal_tax_rate", mode="before")
    @classmethod
    def _rate_as_fraction(cls, v):
        if isinstance(v, str):
            v = float(re.sub(r"[%\s]", "", v) or "nan")
        return v / 100 if isinstance(v, (int, float)) and v > 1 else v


EXTRACT_PROMPT = """אתה מחלץ נתונים מתלוש שכר ישראלי. הטקסט חולץ אוטומטית מ-PDF, ולכן הטבלאות שבורות לשורות.
החזר אך ורק אובייקט JSON תקין עם השדות הבאים (ללא מרקדאון):
{fields}

כללים:
- כל ערך חייב להופיע בתלוש. אל תחשב ואל תנחש. אם שדה לא מופיע, החזר null.
- סכומים כמספרים בלבד, בלי ₪ ובלי פסיקים.
- השתמש בנתוני החודש הנוכחי ולא בעמודת "נתונים מצטברים".
- "גמל מעסיק" או "תגמולי מעסיק" הם pension_employer. "פיצויים" הם severance_employer.
- הפרשת העובד לפנסיה מופיעה בדרך כלל בניכויי החובה בשם הקרן (מבטחים, מגדל, הראל, כלל וכו').
"""


def _fields_doc() -> str:
    return "\n".join(f'- "{name}": {f.description}' for name, f in Payslip.model_fields.items())


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    return json.loads(match.group(0) if match else text)


def extract_payslip(text: str, client, model: str) -> Payslip:
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT.format(fields=_fields_doc())},
            {"role": "user", "content": text},
        ],
    )
    try:
        data = _parse_json(response.choices[0].message.content)
        return Payslip.model_validate({k: v for k, v in data.items() if k in Payslip.model_fields})
    except (json.JSONDecodeError, ValidationError, AttributeError) as e:
        raise ValueError(f"לא הצלחתי לקרוא את התלוש: {e}")


# --- 4. בדיקות חשבון בקוד ---
def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE


def check_payslip(p: Payslip) -> list[str]:
    """מחזיר רשימת אזהרות. רשימה ריקה = המספרים מסתדרים זה עם זה."""
    warnings = []
    if p.net_pay is None and p.net_to_bank is None:
        warnings.append("לא נמצא שכר נטו")
    if p.gross_pay is not None and p.mandatory_deductions_total is not None and p.net_pay is not None:
        if not _close(p.gross_pay - p.mandatory_deductions_total, p.net_pay):
            warnings.append("ברוטו פחות ניכויי חובה לא שווה לנטו")
    if p.net_pay is not None and p.net_to_bank is not None:
        if not _close(p.net_pay - (p.voluntary_deductions_total or 0), p.net_to_bank):
            warnings.append("נטו פחות ניכויי רשות לא שווה לסכום לתשלום")
    parts = [p.income_tax, p.national_insurance, p.health_tax, p.pension_employee, p.study_fund_employee]
    if p.mandatory_deductions_total is not None and any(x is not None for x in parts):
        if not _close(sum(x or 0 for x in parts), p.mandatory_deductions_total):
            warnings.append('סכום רכיבי ניכויי החובה לא שווה לסה"כ')
    if p.period and not re.fullmatch(r"\d{4}-\d{2}", p.period):
        warnings.append("חודש התלוש לא בפורמט YYYY-MM")
    return warnings


def payslip_summary(p: Payslip) -> dict:
    """מה שהסוכן צריך לשיחה: הכנסה פנויה וחיסכון פנסיוני חודשי."""
    def total(*xs):
        vals = [x for x in xs if x is not None]
        return round(sum(vals), 2) if vals else None

    return {
        "period": p.period,
        "employer": p.employer,
        "gross_pay": p.gross_pay,
        "net_to_bank": p.net_to_bank if p.net_to_bank is not None else p.net_pay,
        "pension_monthly_total": total(p.pension_employee, p.pension_employer, p.severance_employer),
        "study_fund_monthly_total": total(p.study_fund_employee, p.study_fund_employer),
        "pension_fund": p.pension_fund,
        "marginal_tax_rate": p.marginal_tax_rate,
    }


# --- הכל יחד ---
PAYSLIP_HINTS = ("תלוש", "שכר נטו", "ניכויי חובה", "נכויי חובה", "לתשלום")


def detect_doc_type(text: str) -> str | None:
    if sum(h in text for h in PAYSLIP_HINTS) >= 2:
        return "payslip"
    return None


def read_document(path: str | Path, client, model: str) -> dict:
    text = pdf_to_text(path)
    doc_type = detect_doc_type(text)
    if doc_type != "payslip":
        raise ValueError("כרגע אפשר לקרוא רק תלושי שכר. דוחות פנסיה ומשכנתא יתווספו בהמשך.")
    slip = extract_payslip(redact(text), client, model)
    return {
        "doc_type": doc_type,
        "period": slip.period,
        "data": slip.model_dump(),
        "summary": payslip_summary(slip),
        "warnings": check_payslip(slip),
    }
