"""עיצוב הממשק: CSS ופונקציות שמייצרות HTML. בלי תלות ב-Gradio, כדי שיהיה קל לבדוק."""
import html
import inspect

from portfolio_copilot.monthly import MonthlyReport, history_row
from portfolio_copilot.proposal import Proposal
from portfolio_copilot.schemas import InvestorProfile, format_money


def esc(value) -> str:
    """כל טקסט שמגיע מהמשתמש או מהמודל עובר escape לפני שהוא נכנס ל-HTML."""
    return html.escape(str(value), quote=True)


def supported(callable_, **kwargs) -> dict:
    """מסנן פרמטרים שהגרסה המותקנת של Gradio לא מכירה, כדי שהקוד יעבוד בכמה גרסאות."""
    try:
        params = inspect.signature(callable_).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in params}


CSS = """
:root {
  --pc-bg:#f4f5fb; --pc-card:#ffffff; --pc-ink:#1c1f3a; --pc-muted:#6b7188; --pc-line:#e4e7f2;
  --pc-primary:#4f46e5; --pc-primary-soft:#eceafd;
  --pc-ok:#0f9f6e; --pc-ok-soft:#e3f6ee; --pc-warn:#a8650b; --pc-warn-soft:#fdf1d8;
  --pc-err:#c53030; --pc-err-soft:#fde8e8;
}
.dark {
  --pc-bg:#12141f; --pc-card:#1b1e2e; --pc-ink:#eceefb; --pc-muted:#9aa1bb; --pc-line:#2a2e45;
  --pc-primary-soft:#2a2860; --pc-ok-soft:#10382b; --pc-warn-soft:#3a2d10; --pc-err-soft:#3d1a1a;
}
.gradio-container {
  direction: rtl; background: var(--pc-bg) !important; max-width: 1280px !important;
  margin: 0 auto !important; font-family: 'Heebo','Segoe UI',Arial,sans-serif !important;
}
.gradio-container .prose, .gradio-container .message, .gradio-container textarea,
.gradio-container input, .gradio-container label { direction: rtl; text-align: right; }
footer { display: none !important; }

.pc-hero {
  direction: rtl; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  background: linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%); color: #fff;
  border-radius: 20px; padding: 26px 30px; margin-bottom: 8px;
  box-shadow: 0 10px 30px rgba(79,70,229,.25);
}
.pc-hero h1 { margin: 0 0 6px; font-size: 30px; font-weight: 800; letter-spacing: -0.5px; color:#fff; direction: ltr; text-align: right; }
.pc-hero p { margin: 0; font-size: 16px; opacity: .92; color:#fff; }
.pc-hero .pc-chip { background: rgba(255,255,255,.18); color: #fff; }

.pc-card {
  direction: rtl; text-align: right; background: var(--pc-card); color: var(--pc-ink);
  border: 1px solid var(--pc-line); border-radius: 18px; padding: 20px 22px;
  box-shadow: 0 2px 10px rgba(28,31,58,.04);
}
.pc-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 16px; }
.pc-card-head h3 { margin: 0; font-size: 19px; font-weight: 700; color: var(--pc-ink); }
.pc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 18px; }
.pc-field { display: flex; flex-direction: column; gap: 4px; }
.pc-field.full { grid-column: 1 / -1; }
.pc-label { font-size: 12.5px; color: var(--pc-muted); font-weight: 500; }
.pc-value { font-size: 16px; font-weight: 600; color: var(--pc-ink); }
.pc-muted { color: var(--pc-muted) !important; font-weight: 400; }
.pc-chips { display: flex; flex-wrap: wrap; gap: 6px; }

.pc-chip { display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; white-space: nowrap; }
.pc-chip-ok { background: var(--pc-ok-soft); color: var(--pc-ok); }
.pc-chip-wait { background: var(--pc-warn-soft); color: var(--pc-warn); }
.pc-chip-idle { background: var(--pc-primary-soft); color: var(--pc-primary); }
.pc-chip-soft { background: var(--pc-primary-soft); color: var(--pc-primary); font-weight: 500; }
.pc-risk-low { background: #e0efff; color: #1d5fb4; }
.pc-risk-mid { background: #dcf5ee; color: #0b7a5b; }
.pc-risk-high { background: #ffe9d6; color: #b4530a; }
.pc-unconfirmed { outline: 2px dashed currentColor; outline-offset: 1px; }

.pc-quote { margin-top: 18px; padding: 12px 14px; border-right: 4px solid var(--pc-primary); background: var(--pc-primary-soft);
  border-radius: 8px; font-size: 14.5px; line-height: 1.6; color: var(--pc-ink); }

.pc-banner { direction: rtl; text-align: right; padding: 10px 14px; border-radius: 12px; margin-bottom: 12px; font-size: 14px; font-weight: 500; }
.pc-banner-ok { background: var(--pc-ok-soft); color: var(--pc-ok); }
.pc-banner-err { background: var(--pc-err-soft); color: var(--pc-err); }
.pc-banner-info { background: var(--pc-primary-soft); color: var(--pc-primary); }
.pc-banner-warn { background: var(--pc-warn-soft); color: var(--pc-warn); }
.pc-banner-warn ul { margin: 6px 0 0; padding-inline-start: 20px; }

.pc-table { width: 100%; border-collapse: collapse; font-size: 15px; }
.pc-table th { text-align: right; font-size: 12.5px; color: var(--pc-muted); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--pc-line); }
.pc-table td { padding: 10px 8px; border-bottom: 1px solid var(--pc-line); color: var(--pc-ink); }
.pc-table tr:last-child td { border-bottom: none; }

.pc-empty { color: var(--pc-muted); font-size: 14.5px; line-height: 1.6; padding: 6px 0; }

.pc-section { margin: 14px 0 2px; font-size: 13px; font-weight: 700; color: var(--pc-muted); }
.pc-steps { direction: rtl; display: flex; gap: 10px; flex-wrap: wrap; margin: 6px 0 4px; }
.pc-step { display: flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: 999px; font-size: 14.5px; font-weight: 600;
  background: var(--pc-card); color: var(--pc-muted); border: 1px solid var(--pc-line); }
.pc-step .pc-step-n { display: inline-flex; width: 24px; height: 24px; border-radius: 50%; align-items: center; justify-content: center;
  background: var(--pc-line); color: var(--pc-ink); font-size: 13px; }
.pc-step-now { background: var(--pc-primary-soft); color: var(--pc-primary); border-color: var(--pc-primary); }
.pc-step-now .pc-step-n { background: var(--pc-primary); color: #fff; }
.pc-step-done { background: var(--pc-ok-soft); color: var(--pc-ok); border-color: transparent; }
.pc-step-done .pc-step-n { background: var(--pc-ok); color: #fff; }
.pc-total { font-size: 28px; font-weight: 800; color: var(--pc-ink); margin: 4px 0 14px; }
.pc-steps-list { margin: 10px 0 0; padding: 0; list-style: none; counter-reset: s; }
.pc-steps-list li { counter-increment: s; position: relative; padding: 12px 52px 12px 12px; margin-bottom: 10px; border-radius: 14px;
  background: var(--pc-primary-soft); color: var(--pc-ink); }
.pc-steps-list li::before { content: counter(s); position: absolute; right: 14px; top: 12px; width: 26px; height: 26px; border-radius: 50%;
  background: var(--pc-primary); color: #fff; font-weight: 700; display: flex; align-items: center; justify-content: center; font-size: 14px; }
.pc-steps-list li b { display: block; font-size: 15.5px; margin-bottom: 2px; }
.pc-steps-list li span { font-size: 14px; color: var(--pc-muted); }
.pc-suggest { border-radius: 999px !important; font-size: 13.5px !important; }
.gradio-container button.primary { font-weight: 700; }
"""


def hero_html() -> str:
    return (
        '<div class="pc-hero"><div>'
        "<h1>Portfolio Copilot</h1>"
        "<p>סוכן השקעות אישי: ראיון, תמונת מצב, הצעה וניהול חודשי</p>"
        "</div>"
        '<span class="pc-chip">פרויקט אקדמי · לא ייעוץ השקעות או פנסיה מורשה</span></div>'
    )


def banner_html(prefix: str) -> str:
    """הודעת מצב קצרה מעל תוכן. ✅ הצלחה, ❌ שגיאה, אחרת מידע."""
    if not prefix:
        return ""
    kind = "ok" if prefix.startswith("✅") else "err" if prefix.startswith("❌") else "info"
    text = prefix.lstrip("✅❌ ").strip()
    return f'<div class="pc-banner pc-banner-{kind}">{esc(text)}</div>'


PAYSLIP_WARNINGS_TITLE = "⚠️ בדיקת החשבון בתלוש מצאה פערים. בדוק את השדות ותקן לפני החישוב:"


def payslip_status_html(message: str, warnings: list[str] | None = None) -> str:
    """הודעת הקריאה של תלוש, ומתחתיה האזהרות של בדיקת החשבון (check_payslip), אם יש."""
    out = banner_html(message)
    if warnings:
        items = "".join(f"<li>{esc(w)}</li>" for w in warnings)
        out += f'<div class="pc-banner pc-banner-warn">{esc(PAYSLIP_WARNINGS_TITLE)}<ul>{items}</ul></div>'
    return out


def _field(label: str, inner: str, full: bool = False) -> str:
    cls = "pc-field full" if full else "pc-field"
    return f'<div class="{cls}"><span class="pc-label">{esc(label)}</span>{inner}</div>'


def _value(text, muted: bool = False) -> str:
    cls = "pc-value pc-muted" if muted else "pc-value"
    return f'<span class="{cls}">{esc(text)}</span>'


def _chips(items, cls: str = "pc-chip-soft") -> str:
    return '<div class="pc-chips">' + "".join(f'<span class="pc-chip {cls}">{esc(i)}</span>' for i in items) + "</div>"


RISK_CLASS = {"שמרני": "pc-risk-low", "מאוזן": "pc-risk-mid", "אגרסיבי": "pc-risk-high"}


def profile_html(profile: InvestorProfile) -> str:
    if profile.is_complete():
        status = '<span class="pc-chip pc-chip-ok">מוכן לחישוב</span>'
    elif profile.recommended_risk_level and not profile.risk_confirmed:
        status = '<span class="pc-chip pc-chip-wait">ממתין לאישור שלך</span>'
    else:
        status = '<span class="pc-chip pc-chip-idle">בבנייה</span>'

    stage = profile.life_stage or ""
    if profile.age is not None:
        stage = f"{stage} · גיל {profile.age}" if stage else f"גיל {profile.age}"
    stage_html = _value(stage) if stage else _value("—", muted=True)

    amounts = []
    if profile.initial_amount:
        amounts.append(f"ראשוני {format_money(profile.initial_amount)}")
    if profile.monthly_deposit:
        amounts.append(f"חודשי {format_money(profile.monthly_deposit)}")
    amount_html = _value(" · ".join(amounts)) if amounts else _value("—", muted=True)

    if profile.needs_cashflow is None:
        cash_html = _value("—", muted=True)
    else:
        cash_html = _value("משיכה חודשית" if profile.needs_cashflow else "צבירה לעתיד")

    if profile.recommended_risk_level:
        cls = RISK_CLASS.get(profile.recommended_risk_level, "pc-chip-idle")
        unconf = "" if profile.risk_confirmed else " pc-unconfirmed"
        suffix = "" if profile.risk_confirmed else " (הצעה)"
        risk_html = f'<span><span class="pc-chip {cls}{unconf}">{esc(profile.recommended_risk_level + suffix)}</span></span>'
    else:
        risk_html = _value("—", muted=True)

    horizon_html = (_value(f"{profile.investment_horizon_years} שנים")
                    if profile.investment_horizon_years else _value("—", muted=True))

    vehicles = _chips(profile.relevant_vehicles) if profile.relevant_vehicles else _value("—", muted=True)
    restrictions = (_chips(profile.restrictions, "pc-chip-wait") if profile.restrictions
                    else _value("אין", muted=True))

    reasoning = (f'<div class="pc-quote">{esc(profile.agent_reasoning)}</div>' if profile.agent_reasoning
                 else '<div class="pc-empty">הסוכן ינמק את ההמלצה שלו במהלך השיחה.</div>')

    return (
        '<div class="pc-card">'
        f'<div class="pc-card-head"><h3>הפרופיל שלי</h3>{status}</div>'
        '<div class="pc-grid">'
        + _field("שלב בחיים", stage_html)
        + _field("היקף השקעה", amount_html)
        + _field("רמת סיכון", risk_html)
        + _field("אופק השקעה", horizon_html)
        + _field("אופי התיק", cash_html)
        + _field("מכשירים רלוונטיים", vehicles, full=True)
        + _field("מגבלות שלי", restrictions, full=True)
        + "</div>" + reasoning + "</div>"
    )


def salary_history_html(events: list[dict], prefix: str = "") -> str:
    head = banner_html(prefix)
    if not events:
        return head + '<div class="pc-card"><div class="pc-card-head"><h3>היסטוריה</h3></div><div class="pc-empty">עדיין לא נרשמו משכורות.</div></div>'
    cells = ("household_net", "total_pension", "total_study_fund", "set_aside", "emergency")
    rows = "".join(
        f'<tr><td>{esc(r["period"])}</td>' + "".join(f"<td>{_amount(r[k])}</td>" for k in cells) + "</tr>"
        for r in map(history_row, events))
    return head + ('<div class="pc-card"><div class="pc-card-head"><h3>היסטוריה</h3></div>'
                   '<table class="pc-table"><tr><th>חודש</th><th>נטו משותף</th><th>פנסיה</th><th>השתלמות</th>'
                   '<th>הופקד</th><th>מזה לקרן חירום</th></tr>' + rows + "</table></div>")


# --- מסע המשתמש: שלבים ותמונת מצב ---
STAGES = [("intake", "היכרות"), ("picture", "המצב שלי"), ("monthly", "ניהול חודשי")]


def stages_html(done: dict) -> str:
    current = next((k for k, _ in STAGES if not done.get(k)), None)
    chips = []
    for i, (key, label) in enumerate(STAGES, 1):
        cls = "pc-step-done" if done.get(key) else "pc-step-now" if key == current else ""
        mark = "✓" if done.get(key) else str(i)
        chips.append(f'<div class="pc-step {cls}"><span class="pc-step-n">{mark}</span>{esc(label)}</div>')
    return '<div class="pc-steps">' + "".join(chips) + "</div>"


# השדות ש-InvestorProfile.missing_fields() מחזיר, בסדר שהסוכן שואל עליהם
PROFILE_FIELD_LABELS = {
    "age": "גיל או שלב בחיים",
    "marital_status": "מצב משפחתי",
    "spouse_monthly_net_income": "הכנסת בן/בת זוג",
    "employment_status": "מצב תעסוקתי",
    "monthly_net_income": "הכנסה נטו חודשית",
    "monthly_expenses": "הוצאות חודשיות",
    "monthly_deposit": "הפקדה חודשית",
    "liquid_savings": "כסף נזיל",
    "monthly_debt_payments": "החזרי חובות",
    "pension_balance": "יתרת פנסיה",
    "study_fund_balance": "יתרת השתלמות",
    "other_assets": "נכסים אחרים",
    "investment_goal": "יעד",
    "investment_horizon_years": "אופק השקעה",
    "recommended_risk_level": "רמת סיכון מוצעת",
    "risk_confirmed": "אישור רמת הסיכון",
}


def intake_progress_html(profile: InvestorProfile) -> str:
    """מה כבר נאסף בשיחת ההיכרות ומה עוד חסר. הנתונים מגיעים מהפרופיל השמור, לא מהמודל."""
    missing = set(profile.missing_fields())
    if not profile.risk_confirmed:  # missing_fields מדלג על האישור כל עוד אין רמת סיכון
        missing.add("risk_confirmed")
    if not missing:
        head = banner_html("✅ הפרופיל מלא ונשמר. אפשר לעבור לשלב הבא: המצב שלי.")
        status = '<span class="pc-chip pc-chip-ok">הושלם</span>'
    else:
        head = ""
        status = f'<span class="pc-chip pc-chip-wait">חסרים {len(missing)}</span>'
    chips = "".join(
        f'<span class="pc-chip {"pc-chip-wait" if key in missing else "pc-chip-ok"}">'
        f'{"◯" if key in missing else "✓"} {esc(label)}</span>'
        for key, label in PROFILE_FIELD_LABELS.items()
        if key != "spouse_monthly_net_income" or profile.is_partnered())
    return head + ('<div class="pc-card"><div class="pc-card-head"><h3>התקדמות ההיכרות</h3>' + status + "</div>"
                   f'<div class="pc-chips">{chips}</div></div>')


def situation_html(view: dict, prefix: str = "") -> str:
    """מציג את תמונת המצב של שלב 2 (situation.build_situation). הערכים והמקורות כבר מחושבים שם."""
    head = banner_html(prefix)
    total = (f'<div class="pc-total">{format_money(view["total"])}</div>' if view.get("total") is not None
             else '<div class="pc-empty">עדיין אין נכסים ידועים לסיכום.</div>')
    body = ""
    for section in view["sections"]:
        rows = "".join(
            f'<tr><td>{esc(r["label"])}</td>'
            f'<td>{_value(r["display"], muted=r["value"] is None)}'
            + (f'<div class="pc-empty">{esc(r["detail"])}</div>' if r.get("detail") else "") + "</td>"
            f'<td>{_chips([x for x in (r["source"], r.get("added_source")) if x]) if r["source"] or r.get("added_source") else ""}</td></tr>'
            for r in section["rows"])
        body += (f'<div class="pc-section">{esc(section["title"])}</div>'
                 '<table class="pc-table"><tr><th>נתון</th><th>ערך</th><th>מקור</th></tr>' + rows + "</table>")
    gaps = ""
    if view.get("gaps"):
        gaps = ('<div class="pc-section">מה עוד חסר לתמונה מלאה</div><ul style="margin:0;padding-right:20px;line-height:1.8">'
                + "".join(f"<li>{esc(g)}</li>" for g in view["gaps"]) + "</ul>")
    return head + ('<div class="pc-card"><div class="pc-card-head"><h3>תמונת המצב שלי</h3>'
                   '<span class="pc-chip pc-chip-idle">שווי נכסים ידוע</span></div>' + total + body + gaps + "</div>")


# --- קבל הצעה (proposal.build_proposal) ---
def _amount(x) -> str:
    return format_money(x) if x is not None else "—"


def _card(title: str, inner: str) -> str:
    return f'<div class="pc-card" style="margin-top:12px"><div class="pc-card-head"><h3>{esc(title)}</h3></div>{inner}</div>'


def _bullets(items) -> str:
    return '<ul style="margin:0;padding-right:20px;line-height:1.8">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


NOT_COMPUTED = '<div class="pc-empty">לא חושב: חסרים נתונים (ראה "מה חסר").</div>'


def proposal_html(p: Proposal) -> str:
    """מציג את ההצעה בשלושה חלקים. כל המספרים והמשפטים כבר חושבו ב-proposal.py."""
    # 1. ביטחון
    s = p.safety
    if s is None:
        safety = NOT_COMPUTED
    else:
        fields = []
        if s.emergency_target_months is not None:
            fields += [_field("יעד קרן חירום", _value(f"{s.emergency_target_months} חודשים · {_amount(s.emergency_target_amount)}")),
                       _field("מכוסה היום", _value(f"{s.current_months} חודשים" if s.current_months is not None else "—")),
                       _field("חסר", _value(_amount(s.shortfall))),
                       _field("זמן למילוי", _value(f"כ-{s.months_to_fill} חודשים" if s.months_to_fill else "—"))]
        if s.debt_ratio is not None:
            fields.append(_field("החזר חובות מהנטו", _value(f"{s.debt_ratio:.0%}")))
        safety = f'<div class="pc-grid">{"".join(fields)}</div>'
        safety += (_bullets(s.steps) if s.steps else '<div class="pc-empty">אין צעד ביטחון דחוף.</div>')

    # 2. ההון הקיים
    c = p.capital
    if c is None:
        capital = NOT_COMPUTED
    else:
        rows = "".join(f'<tr><td>{esc(line.asset_class)}</td><td>{line.percent:g}%</td>'
                       f'<td>{_amount(line.existing_amount)}</td><td>{_amount(line.monthly_amount)}</td></tr>'
                       for line in c.allocation)
        capital = (f'<div class="pc-grid">{_field("מניות בתמהיל", _value(f"{c.equity_percent:g}%"))}'
                   f'{_field("עודף נזיל להשקעה", _value(_amount(c.liquid_surplus)))}'
                   f'{_field("הפקדה חודשית", _value(_amount(c.monthly_deposit)))}</div>'
                   '<table class="pc-table" style="margin-top:12px"><tr><th>סוג נכס</th><th>אחוז</th>'
                   '<th>מהעודף הנזיל</th><th>מההפקדה החודשית</th></tr>' + rows + "</table>")

    # 3. פנסיה והשתלמות
    pension = NOT_COMPUTED if p.pension is None else (
        f'<div class="pc-grid">{_field("קרן פנסיה: מסלול", _value(p.pension.pension_track))}'
        f'{_field("קרן השתלמות: מסלול", _value(p.pension.study_fund_track))}</div>'
        '<div class="pc-empty">המלצה על מסלול השקעה, לא על קופה או חברה מסוימת.</div>')

    missing = ""
    if p.missing:
        labels = [PROFILE_FIELD_LABELS.get(m, m) for m in p.missing]
        missing = _card("מה חסר כדי להשלים את ההצעה", _bullets(labels))
    notes = _card("הערות", _bullets(p.notes)) if p.notes else ""
    reasons = _card("על מה ההצעה מבוססת", _bullets(p.reasons)) if p.reasons else ""
    return (banner_html("הצעה בסוגי נכסים, מחושבת בקוד לפי הפרופיל שלך. ההחלטה שלך.")
            + '<div class="pc-empty">לפי המצב שהוזן בראיון</div>' + missing
            + _card("1. ביטחון: קרן חירום וחובות", safety) + _card("2. ההון הקיים", capital)
            + _card("3. פנסיה והשתלמות", pension) + notes + reasons)


# --- דיווח חודשי (proposal.monthly_report) ---
def monthly_report_html(r: MonthlyReport) -> str:
    """מה לעשות עם הסכום להשקעה החודש, ולמה. כל המספרים חושבו ב-proposal.py."""
    a = r.allocation
    rows = []
    if a.emergency_amount:
        rows.append(f'<tr><td>קרן חירום ({esc(a.emergency_asset_class)})</td><td>{format_money(a.emergency_amount)}</td></tr>')
    rows += [f'<tr><td>{esc(line.asset_class)}</td><td>{format_money(line.amount)}</td></tr>'
             for line in (a.lines or []) if line.amount]
    if a.unallocated:
        rows.append(f'<tr><td>לא חולק (חסרים נתונים)</td><td>{format_money(a.unallocated)}</td></tr>')
    table = ('<table class="pc-table"><tr><th>לאן</th><th>סכום</th></tr>' + "".join(rows) + "</table>")
    base = (_field("האחוז חושב על", _value(r.percent_base)) if r.percent_base else "")
    has_partner = any(v is not None for v in (r.partner_net, r.partner_pension, r.partner_study_fund))
    partner = ""
    if has_partner:
        partner = (_field("נטו: שלך · בן/בת הזוג · משותף",
                          _value(f"{format_money(r.net)} · {_amount(r.partner_net)} · {format_money(r.household_net)}"))
                   + _field("פנסיה: שלך · בן/בת הזוג · סה\"כ",
                            _value(f"{format_money(r.pension_contributions)} · {_amount(r.partner_pension)} · {format_money(r.total_pension)}"))
                   + _field("השתלמות: שלך · בן/בת הזוג · סה\"כ",
                            _value(f"{format_money(r.study_fund_contributions)} · {_amount(r.partner_study_fund)} · {format_money(r.total_study_fund)}")))
    summary = (f'<div class="pc-grid" style="margin-top:12px">{base}{partner}{_field("נשאר להוצאות", _value(format_money(r.free_to_spend)))}'
               f'{_field("הפקדות לפנסיה ולהשתלמות", _value(f"{format_money(r.total_pension)} · {format_money(r.total_study_fund)}"))}'
               f'{_field("סך החיסכון החודש", _value(format_money(r.total_saved_this_month)))}</div>')
    missing = ""
    if a.missing:
        missing = ('<div class="pc-section">מה חסר בפרופיל</div>'
                   + _bullets([PROFILE_FIELD_LABELS.get(m, m) for m in a.missing]))
    why = '<div class="pc-section">למה</div>' + _bullets(a.reasons)
    return (f'<div class="pc-card"><div class="pc-card-head"><h3>דיווח חודשי: {esc(r.period)}</h3>'
            f'<span class="pc-chip pc-chip-idle">נטו {esc(format_money(r.household_net))}</span></div>'
            '<div class="pc-empty">הצעה לאישור, בסוגי נכסים. לא בוצע כלום, ואין הצעות מכירה.</div>'
            f'<div class="pc-section">מה לעשות עם {esc(format_money(r.set_aside))}</div>{table}{summary}{missing}{why}</div>')
