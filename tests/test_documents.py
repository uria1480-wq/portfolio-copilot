import json
from types import SimpleNamespace

import pytest

from portfolio_copilot import documents
from portfolio_copilot.agent_tools import run_tool
from portfolio_copilot.db import Store
from portfolio_copilot.documents import (Payslip, check_payslip, detect_doc_type, extract_payslip,
                                         fix_hebrew_order, read_document, redact)
from portfolio_copilot.schemas import InvestorProfile

# תלוש בדוי (לא של אדם אמיתי), בפריסה דומה למה ש-pdfplumber מחזיר
SLIP_TEXT = """חברה : 001 - חברה לדוגמה בע"מ תיק ניכויים: 912345678 תלוש שכר לחודש 09/2026
פרטים אישיים
מספר זהות: 123456782 מספר העובד: 0042
בנק: 12/345 חשבון: 000123456
תאור התשלום עבור כמות תעריף גילום שווי למס התשלום נכויי חובה הניכוי
001 משכורת 160.00 50.00 8000.00 ב.לאומי 300.00
מס בריאות 400.00
מס הכנסה 500.00
מגדל פנסיה 480.00
סה"כ תשלומים 8000.00 ניכויי חובה 1680.00
שכר נטו 6320.00
אחוז מס שולי 20% גמל מעסיק 520.00 לפיצ. 500.00
18 ועד 20.00 נכויי רשות 20.00
לתשלום 6300.00"""

GOOD = {
    "period": "2026-09", "employer": "חברה לדוגמה", "gross_pay": "8,000.00",
    "income_tax": 500, "national_insurance": 300, "health_tax": 400, "pension_employee": 480,
    "mandatory_deductions_total": 1680, "net_pay": 6320, "voluntary_deductions_total": 20,
    "net_to_bank": "₪6,300", "pension_employer": 520, "severance_employer": 500,
    "pension_fund": "מגדל", "marginal_tax_rate": "20%", "made_up_field": 1,
}


class FakeClient:
    def __init__(self, content):
        self.content, self.messages = content, None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.messages = kwargs["messages"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def test_hebrew_visual_order_is_fixed():
    assert fix_hebrew_order("םולשתל 6300.00") == "6300.00 לתשלום"
    assert fix_hebrew_order("לתשלום 6300.00") == "לתשלום 6300.00"  # כבר תקין, לא נוגעים


def test_redact_hides_ids_and_bank_details():
    out = redact(SLIP_TEXT)
    for secret in ("123456782", "000123456", "912345678", "12/345"):
        assert secret not in out
    assert "6300.00" in out and "8000.00" in out  # סכומים נשארים


def test_extract_cleans_numbers_and_ignores_unknown_fields():
    slip = extract_payslip("טקסט", FakeClient("```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```"), "m")
    assert slip.gross_pay == 8000.0 and slip.net_to_bank == 6300.0
    assert slip.marginal_tax_rate == pytest.approx(0.20)


def test_extract_bad_json_raises_value_error():
    with pytest.raises(ValueError):
        extract_payslip("טקסט", FakeClient("לא JSON"), "m")


def test_arithmetic_checks():
    slip = Payslip.model_validate(GOOD)
    assert check_payslip(slip) == []
    wrong = slip.model_copy(update={"net_pay": 7000.0})
    assert len(check_payslip(wrong)) >= 2  # גם ברוטו-ניכויים וגם נטו-רשות לא מסתדרים
    assert check_payslip(Payslip()) == ["לא נמצא שכר נטו"]


def test_read_document_sends_only_redacted_text(monkeypatch):
    monkeypatch.setattr(documents, "pdf_to_text", lambda path: SLIP_TEXT)
    fake = FakeClient(json.dumps(GOOD, ensure_ascii=False))
    doc = read_document("x.pdf", fake, "m")
    assert "123456782" not in fake.messages[1]["content"]
    assert doc["doc_type"] == "payslip" and doc["warnings"] == []
    assert doc["summary"]["net_to_bank"] == 6300.0
    assert doc["summary"]["pension_monthly_total"] == 1500.0  # 480 + 520 + 500


def test_non_payslip_is_rejected(monkeypatch):
    monkeypatch.setattr(documents, "pdf_to_text", lambda path: "דוח שנתי מקוצר לעמית בקרן הפנסיה")
    assert detect_doc_type("דוח שנתי") is None
    with pytest.raises(ValueError, match="תלושי שכר"):
        read_document("x.pdf", FakeClient("{}"), "m")


def _doc(period, net):
    slip = Payslip.model_validate({**GOOD, "period": period, "net_to_bank": net, "net_pay": net + 20,
                                   "gross_pay": net + 1700})
    return {"doc_type": "payslip", "period": period, "data": slip.model_dump(),
            "summary": documents.payslip_summary(slip), "warnings": check_payslip(slip)}


def test_store_keeps_one_slip_per_month_newest_first():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    s.save_document(uid, _doc("2026-08", 6000.0))
    s.save_document(uid, _doc("2026-09", 6300.0))
    s.save_document(uid, _doc("2026-09", 6400.0))  # העלאה חוזרת של אותו חודש מחליפה
    docs = s.list_documents(uid, "payslip")
    assert [d["period"] for d in docs] == ["2026-09", "2026-08"]
    assert docs[0]["summary"]["net_to_bank"] == 6400.0


def test_get_documents_tool():
    s = Store(":memory:")
    uid = s.get_or_create_user("demo")
    assert run_tool("get_documents", {}, s, uid, InvestorProfile())["payslips"] == []
    s.save_document(uid, _doc("2026-08", 6000.0))
    s.save_document(uid, _doc("2026-09", 6400.0))
    r = run_tool("get_documents", {}, s, uid, InvestorProfile())
    assert r["avg_net_to_bank"] == 6200.0 and r["payslips"][0]["period"] == "2026-09"
