import json
from types import SimpleNamespace

import pytest

from portfolio_copilot import fund_reports
from portfolio_copilot.fund_reports import (FundReport, check_fund_report, classify_fund_type, clean_text, detect_fund_report,
                                            fund_report_summary, quarter_key, read_any_document,
                                            read_fund_report, redact_report)

# טקסט בדוי שמדמה את מבנה הדוח, כולל סימוני כיווניות שמגיעים מה-PDF
TEXT = (
    "\u202bדוח רבעוני לעמית בקופת הגמל להשקעה דוגמה קופת גמל להשקעה\u202c\n"
    "לסוף הרבעון ה- 1 לשנת 2026 מתאריך 01/01/26 עד תאריך 31/03/26\n"
    "שם העמית: ישראל ישראלי מספר ת\u202a.\u202cז. 12345678/9 מספר חשבון: 99887766\n"
    "תנועות בחשבונך בתקופת הדיווח\n"
    "יתרת הכספים בחשבון בתחילת השנה 100,000\n"
    "דמי ניהול מחיסכון 0.40%\n"
    "יתרת הכספים בחשבון בסוף תקופת הדיווח 103,900\n"
)

GOOD = dict(period_end="2026-03-31", report_date="2026-03-31", balance_start=100000, deposits=0,
            net_returns=4000, management_fees_charged=-100, balance_end=103900,
            fee_on_savings_pct=0.40, avg_fee_on_savings_pct=0.60, expected_annual_cost_pct=0.70)


def test_clean_text_removes_bidi_controls():
    assert clean_text("\u202bשלום\u202c \u200e1\u200f") == "שלום 1"


def test_redaction_masks_name_id_and_account_but_keeps_numbers():
    out = redact_report(TEXT)
    for secret in ("ישראל", "ישראלי", "12345678", "99887766"):
        assert secret not in out
    assert "100,000" in out and "103,900" in out and "0.40%" in out


def test_detection():
    assert detect_fund_report(TEXT)
    assert not detect_fund_report("תלוש שכר נטו לתשלום ניכויי חובה ברוטו")


def test_numbers_are_cleaned():
    r = FundReport(balance_end="103,900", management_fees_charged="100-", fee_on_savings_pct="0.40%", deposits="\u221250")
    assert (r.balance_end, r.management_fees_charged, r.fee_on_savings_pct, r.deposits) == (103900.0, -100.0, 0.40, -50.0)


def test_consistent_report_has_no_warnings():
    assert check_fund_report(FundReport(**GOOD)) == []


def test_arithmetic_and_fee_mismatches_are_flagged():
    assert any("יתרת הסוף" in w for w in check_fund_report(FundReport(**{**GOOD, "balance_end": 110000})))
    assert any("דמי הניהול שנגבו" in w for w in check_fund_report(FundReport(**{**GOOD, "management_fees_charged": -300, "balance_end": 103700})))
    assert check_fund_report(FundReport(balance_start=1)) == ["לא נמצאה יתרת סוף תקופה"]


def test_fee_sign_convention_does_not_matter():
    assert check_fund_report(FundReport(**{**GOOD, "management_fees_charged": 100})) == []


def test_summary_and_quarter_key():
    s = fund_report_summary(FundReport(**GOOD))
    assert s["period"] == "2026-Q1" and s["fees_ytd"] == 100 and s["fee_vs_avg_pp"] == -0.2
    assert quarter_key("2026-12-31") == "2026-Q4" and quarter_key("לא תאריך") is None and quarter_key(None) is None


def fake_client(payload):
    msg = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), seen


def test_read_fund_report_end_to_end_and_never_sends_identifiers():
    payload = {**GOOD, "balance_start": "100,000", "management_fees_charged": "-100", "provider": "דוגמה", "fund_name": "קופה לדוגמה"}
    client, seen = fake_client(payload)
    doc = read_fund_report(TEXT, client, "m")
    assert doc["doc_type"] == "fund_report" and doc["period"] == "2026-Q1" and doc["warnings"] == []
    sent = json.dumps(seen[0]["messages"], ensure_ascii=False)
    assert "12345678" not in sent and "99887766" not in sent and "ישראלי" not in sent


def test_bad_model_output_raises_a_clear_error():
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="לא JSON"))]))))
    with pytest.raises(ValueError, match="לא הצלחתי לקרוא את הדוח"):
        read_fund_report(TEXT, client, "m")


def test_read_any_document_routes_by_type(monkeypatch):
    client, _ = fake_client(GOOD)
    monkeypatch.setattr(fund_reports, "pdf_to_text", lambda p: TEXT)
    assert read_any_document("x.pdf", client, "m")["doc_type"] == "fund_report"

    monkeypatch.setattr(fund_reports, "pdf_to_text", lambda p: "תלוש שכר נטו לתשלום ניכויי חובה")
    monkeypatch.setattr(fund_reports, "read_document", lambda p, c, m: {"doc_type": "payslip"})
    assert read_any_document("x.pdf", client, "m") == {"doc_type": "payslip"}

    monkeypatch.setattr(fund_reports, "pdf_to_text", lambda p: "מסמך אחר לגמרי")
    with pytest.raises(ValueError, match="לא זיהיתי"):
        read_any_document("x.pdf", client, "m")


def test_fund_type_is_classified_in_code():
    assert classify_fund_type("\u202bדוח רבעוני בקופת הגמל להשקעה") == "provident_investment"
    assert classify_fund_type("דוח לעמית בקרן השתלמות") == "study_fund"
    assert classify_fund_type("דוח לעמית בקרן פנסיה מקיפה") == "pension"
    assert classify_fund_type("דוח לעמית בקופת גמל") == "provident"
    assert classify_fund_type("מסמך אחר") is None


def test_read_fund_report_sets_the_type_even_if_the_model_gets_it_wrong():
    client, _ = fake_client({**GOOD, "fund_type": "pension"})
    doc = read_fund_report(TEXT, client, "m")
    assert doc["summary"]["fund_type"] == "provident_investment"