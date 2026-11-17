"""קריאת דוח רבעוני מקופת גמל, קרן השתלמות או קרן פנסיה (PDF).

אותה שיטה כמו בתלושים: חילוץ טקסט בקוד, הסתרת פרטים מזהים, חילוץ בעזרת LLM למבנה קבוע,
ובדיקות חשבון בקוד. הקובץ עצמו לא נשמר, רק המספרים.
"""
import json
import re
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from portfolio_copilot.documents import detect_doc_type, pdf_to_text, read_document, redact

# סימוני כיווניות שמוטמעים בטקסט של ה-PDF ושוברים חיפוש לפי מילים
BIDI_CONTROLS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
TOLERANCE = 2.0  # הדוחות מעוגלים לשקל
FEE_TOLERANCE_PP = 0.15  # סטייה מותרת (באחוזים) בין דמי הניהול שנגבו לשיעור המוצהר


def clean_text(text: str) -> str:
    return BIDI_CONTROLS.sub("", text)


# --- הסתרת פרטים מזהים ---
NAME_AFTER_LABEL = re.compile(r"(שם (?:העמית|העמיתה|העובד|הלקוח|בעל החשבון)\s*:?\s*)(.+?)(?=\s+(?:מספר|ת\.?\s?ז|מס'|ח\.?פ)|\n|$)")


def redact_report(text: str) -> str:
    """מסיר ת"ז, מספר חשבון ושם העמית לפני ששולחים את הטקסט למודל."""
    text = redact(clean_text(text))
    return NAME_AFTER_LABEL.sub(r"\1[הוסתר]", text)


# --- סכמה ---
FLOAT_FIELDS = (
    "balance_start", "deposits", "net_returns", "management_fees_charged", "balance_end",
    "fee_on_deposit_pct", "fee_on_savings_pct", "expected_annual_cost_pct",
    "avg_fee_on_deposit_pct", "avg_fee_on_savings_pct", "track_return_pct",
)


class FundReport(BaseModel):
    """שדות מדוח רבעוני של גוף מוסדי. סכומים בשקלים, אחוזים כמספר (0.39 הוא 0.39%). null אם לא מופיע."""

    report_date: Optional[str] = Field(default=None, description="תאריך הדוח בפורמט YYYY-MM-DD")
    period_start: Optional[str] = Field(default=None, description="תחילת תקופת הדיווח, YYYY-MM-DD")
    period_end: Optional[str] = Field(default=None, description="סוף תקופת הדיווח, YYYY-MM-DD")
    provider: Optional[str] = Field(default=None, description="שם החברה המנהלת")
    fund_name: Optional[str] = Field(default=None, description="שם הקופה או הקרן")
    fund_type: Optional[str] = Field(default=None, description="סוג המוצר: pension (קרן פנסיה), study_fund (קרן השתלמות), provident (קופת גמל), provident_investment (גמל להשקעה), other")
    balance_start: Optional[float] = Field(default=None, description="יתרת הכספים בתחילת השנה")
    deposits: Optional[float] = Field(default=None, description="כספים שהופקדו לחשבון בתקופה")
    net_returns: Optional[float] = Field(default=None, description="רווחים (או הפסדים) בניכוי הוצאות ניהול השקעות")
    management_fees_charged: Optional[float] = Field(default=None, description="דמי ניהול שנגבו, כפי שמופיע בדוח (לרוב שלילי)")
    balance_end: Optional[float] = Field(default=None, description="יתרת הכספים בסוף תקופת הדיווח")
    fee_on_deposit_pct: Optional[float] = Field(default=None, description="דמי ניהול מהפקדה באחוזים")
    fee_on_savings_pct: Optional[float] = Field(default=None, description="דמי ניהול מחיסכון באחוזים (שנתי)")
    expected_annual_cost_pct: Optional[float] = Field(default=None, description="עלות שנתית צפויה באחוזים")
    avg_fee_on_deposit_pct: Optional[float] = Field(default=None, description="ממוצע דמי הניהול בקופה מהפקדה, אם מופיע")
    avg_fee_on_savings_pct: Optional[float] = Field(default=None, description="ממוצע דמי הניהול בקופה מחיסכון, אם מופיע")
    track_name: Optional[str] = Field(default=None, description="שם מסלול ההשקעה")
    track_return_pct: Optional[float] = Field(default=None, description="תשואת המסלול בתקופה, באחוזים")
    no_beneficiaries: Optional[bool] = Field(default=None, description="true אם כתוב שלא נקבעו מוטבים בחשבון")

    @field_validator("*", mode="before")
    @classmethod
    def _clean_number(cls, v, info):
        """המודל לפעמים מחזיר '101,882' או '0.39%' או מינוס יוניקוד. ממירים למספר."""
        if isinstance(v, str) and info.field_name in FLOAT_FIELDS:
            cleaned = re.sub(r"[₪,%\s]", "", v.replace("\u2212", "-"))
            if cleaned.endswith("-"):  # מינוס בסוף המספר
                cleaned = "-" + cleaned[:-1]
            return float(cleaned) if cleaned else None
        return v


EXTRACT_PROMPT = """אתה מחלץ נתונים מדוח רבעוני לעמית של קופת גמל, קרן השתלמות או קרן פנסיה בישראל.
הטקסט חולץ אוטומטית מ-PDF, ולכן הטבלאות שבורות לשורות והעמודות עשויות להיות מעורבבות.
החזר אך ורק אובייקט JSON תקין עם השדות הבאים (ללא מרקדאון):
{fields}

כללים:
- כל ערך חייב להופיע בדוח. אל תחשב ואל תנחש. אם שדה לא מופיע, החזר null.
- סכומים כמספרים בלבד, בלי ₪ ובלי פסיקים. אחוזים כמספר: 0.39% הוא 0.39.
- "דמי ניהול שנגבו" מוחזרים כפי שהם מודפסים, כולל סימן מינוס.
- תאריכים בפורמט YYYY-MM-DD.
- "ממוצע דמי ניהול בקופה" מופיע לעיתים בהערה בשוליים.
"""


def _fields_doc() -> str:
    return "\n".join(f'- "{name}": {f.description}' for name, f in FundReport.model_fields.items())


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    return json.loads(match.group(0) if match else text, strict=False)


def extract_fund_report(text: str, client, model: str) -> FundReport:
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
        return FundReport.model_validate({k: v for k, v in data.items() if k in FundReport.model_fields})
    except (json.JSONDecodeError, ValidationError, AttributeError) as e:
        raise ValueError(f"לא הצלחתי לקרוא את הדוח: {e}")


# --- בדיקות חשבון בקוד ---
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def quarter_key(period_end: str | None) -> str | None:
    if not period_end or not DATE_RE.fullmatch(period_end):
        return None
    year, month = int(period_end[:4]), int(period_end[5:7])
    if not 1 <= month <= 12:
        return None
    return f"{year}-Q{(month - 1) // 3 + 1}"


def check_fund_report(r: FundReport) -> list[str]:
    """רשימת אזהרות. רשימה ריקה = המספרים מסתדרים זה עם זה."""
    warnings = []
    if r.balance_end is None:
        warnings.append("לא נמצאה יתרת סוף תקופה")
    for name, value in (("period_end", r.period_end), ("report_date", r.report_date)):
        if value and not DATE_RE.fullmatch(value):
            warnings.append("תאריך לא בפורמט YYYY-MM-DD")
            break

    if r.balance_start is not None and r.balance_end is not None and r.net_returns is not None:
        expected = r.balance_start + (r.deposits or 0) + r.net_returns - abs(r.management_fees_charged or 0)
        if abs(expected - r.balance_end) > TOLERANCE:
            warnings.append("יתרת הפתיחה בתוספת ההפקדות והרווחים פחות דמי הניהול לא שווה ליתרת הסוף")

    # דמי הניהול שנגבו (מתחילת השנה) מול השיעור השנתי המוצהר
    if (r.management_fees_charged and r.fee_on_savings_pct and r.balance_start is not None
            and r.balance_end is not None and r.period_end and DATE_RE.fullmatch(r.period_end)):
        months = int(r.period_end[5:7])
        avg_balance = (r.balance_start + r.balance_end) / 2
        if months and avg_balance > 0:
            annualized = abs(r.management_fees_charged) * (12 / months) / avg_balance * 100
            if abs(annualized - r.fee_on_savings_pct) > FEE_TOLERANCE_PP:
                warnings.append(
                    f"דמי הניהול שנגבו מתאימים לכ-{annualized:.2f}% בשנה, אבל בדוח מופיע {r.fee_on_savings_pct:.2f}%")
    return warnings


FUND_TYPES = {"pension", "study_fund", "provident", "provident_investment", "other"}


def classify_fund_type(text: str) -> str | None:
    """סוג המוצר מזוהה מהטקסט בקוד, כי זה אמין יותר ממודל. הסדר חשוב: גמל להשקעה לפני גמל רגיל."""
    t = clean_text(text)
    if "גמל להשקעה" in t:
        return "provident_investment"
    if "השתלמות" in t:
        return "study_fund"
    if "קרן פנסיה" in t or "פנסיה מקיפה" in t or "פנסיה כללית" in t:
        return "pension"
    if "קופת גמל" in t or "קופת הגמל" in t:
        return "provident"
    return None


def fund_report_summary(r: FundReport) -> dict:
    """מה שהסוכן צריך לשיחה: יתרה, עלויות ומסלול."""
    fee_vs_avg = None
    if r.fee_on_savings_pct is not None and r.avg_fee_on_savings_pct is not None:
        fee_vs_avg = round(r.fee_on_savings_pct - r.avg_fee_on_savings_pct, 2)
    return {
        "doc_type": "fund_report",
        "period": quarter_key(r.period_end),
        "provider": r.provider,
        "fund_name": r.fund_name,
        "fund_type": r.fund_type,
        "report_date": r.report_date,
        "balance_end": r.balance_end,
        "deposits_ytd": r.deposits,
        "net_returns_ytd": r.net_returns,
        "fees_ytd": abs(r.management_fees_charged) if r.management_fees_charged is not None else None,
        "fee_on_savings_pct": r.fee_on_savings_pct,
        "fee_on_deposit_pct": r.fee_on_deposit_pct,
        "avg_fee_on_savings_pct": r.avg_fee_on_savings_pct,
        "fee_vs_avg_pp": fee_vs_avg,
        "expected_annual_cost_pct": r.expected_annual_cost_pct,
        "track_name": r.track_name,
        "track_return_pct": r.track_return_pct,
        "no_beneficiaries": r.no_beneficiaries,
    }


# --- זיהוי סוג המסמך והכל יחד ---
FUND_REPORT_HINTS = ("דוח רבעוני", "קופת גמל", "קרן השתלמות", "קרן פנסיה", "דמי ניהול", "תנועות בחשבונך", "יתרת הכספים")


def detect_fund_report(text: str) -> bool:
    return sum(h in text for h in FUND_REPORT_HINTS) >= 3


def read_fund_report(text: str, client, model: str) -> dict:
    report = extract_fund_report(redact_report(text), client, model)
    report.fund_type = classify_fund_type(text) or (report.fund_type if report.fund_type in FUND_TYPES else None)
    summary = fund_report_summary(report)
    return {
        "doc_type": "fund_report",
        "period": summary["period"],
        "data": report.model_dump(),
        "summary": summary,
        "warnings": check_fund_report(report),
    }


def read_any_document(path, client, model: str) -> dict:
    """תלוש שכר או דוח רבעוני מקופה. סוג המסמך מזוהה אוטומטית."""
    text = clean_text(pdf_to_text(path))
    if detect_fund_report(text):
        return read_fund_report(text, client, model)
    if detect_doc_type(text) == "payslip":
        return read_document(path, client, model)
    raise ValueError("לא זיהיתי את סוג המסמך. כרגע נתמכים תלוש שכר ודוח רבעוני מקופת גמל, קרן השתלמות או פנסיה.")