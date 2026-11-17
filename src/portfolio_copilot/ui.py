"""עיצוב הממשק: CSS ופונקציות שמייצרות HTML. בלי תלות ב-Gradio, כדי שיהיה קל לבדוק."""
import html
import inspect

from portfolio_copilot.analysis import Guidance
from portfolio_copilot.plan import SavingsPlan
from portfolio_copilot.schemas import InvestorProfile


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

.pc-table { width: 100%; border-collapse: collapse; font-size: 15px; }
.pc-table th { text-align: right; font-size: 12.5px; color: var(--pc-muted); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--pc-line); }
.pc-table td { padding: 10px 8px; border-bottom: 1px solid var(--pc-line); color: var(--pc-ink); }
.pc-table tr:last-child td { border-bottom: none; }
.pc-sym { direction: ltr; text-align: right; font-weight: 700; font-family: ui-monospace, Consolas, monospace; }

.pc-doc { padding: 12px 0; border-bottom: 1px solid var(--pc-line); }
.pc-doc:last-child { border-bottom: none; }
.pc-doc b { font-size: 15.5px; }
.pc-doc .pc-row { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 6px; color: var(--pc-muted); font-size: 14px; }
.pc-doc .pc-row span b { color: var(--pc-ink); }
.pc-empty { color: var(--pc-muted); font-size: 14.5px; line-height: 1.6; padding: 6px 0; }

.pc-section { margin: 14px 0 2px; font-size: 13px; font-weight: 700; color: var(--pc-muted); }
.pc-actions { list-style: none; margin: 10px 0 0; padding: 0; }
.pc-actions li { padding: 10px 12px; margin-bottom: 8px; border-radius: 12px; background: var(--pc-primary-soft); color: var(--pc-ink); font-size: 15px; }
.pc-actions li b { font-weight: 700; }
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
        "<p>סוכן פיננסי אישי שמכיר אותך, קורא את המסמכים שלך ומחשב את ההצעה בקוד</p>"
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


def _money(x) -> str:
    return f"₪{x:,.0f}"


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
        amounts.append(f"ראשוני {_money(profile.initial_amount)}")
    if profile.monthly_deposit:
        amounts.append(f"חודשי {_money(profile.monthly_deposit)}")
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
    cap = profile.max_single_asset_weight or 0.20
    cap_html = _value(f"{cap * 100:.0f}% לנכס בודד")

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
        + _field("תקרת פיזור", cap_html)
        + _field("מכשירים רלוונטיים", vehicles, full=True)
        + _field("מגבלות שלי", restrictions, full=True)
        + "</div>" + reasoning + "</div>"
    )


def holdings_html(holdings: list[dict], prefix: str = "") -> str:
    head = banner_html(prefix)
    if not holdings:
        return head + '<div class="pc-card"><div class="pc-card-head"><h3>ההחזקות שלי</h3></div>' \
                      '<div class="pc-empty">עדיין לא נטענו החזקות. העלה קובץ CSV עם העמודות symbol, quantity ו-avg_cost.</div></div>'
    rows = "".join(
        f'<tr><td class="pc-sym">{esc(h["symbol"])}</td><td>{h["quantity"]:g}</td>'
        f'<td>{_money(h["avg_cost"]) if h.get("avg_cost") is not None else "—"}</td></tr>'
        for h in holdings
    )
    return (head + '<div class="pc-card"><div class="pc-card-head"><h3>ההחזקות שלי</h3></div>'
            '<table class="pc-table"><tr><th>סימול</th><th>כמות</th><th>עלות ממוצעת</th></tr>'
            + rows + "</table></div>")


def _pct(x) -> str:
    return f"{x:.2f}%"


def _slip_card(d: dict) -> str:
    s = d["summary"]
    net = _money(s["net_to_bank"]) if s.get("net_to_bank") is not None else "לא נמצא"
    pension = _money(s["pension_monthly_total"]) if s.get("pension_monthly_total") is not None else "לא נמצא"
    warn = ""
    if d.get("warnings"):
        warn = '<div style="margin-top:8px">' + _chips(["לבדוק מול התלוש: " + "; ".join(d["warnings"])], "pc-chip-wait") + "</div>"
    return (
        f'<div class="pc-doc"><b>{esc(s.get("period") or "חודש לא ידוע")}</b>'
        f'<div class="pc-row"><span>נטו לתשלום <b>{esc(net)}</b></span>'
        f'<span>הפרשה חודשית לפנסיה <b>{esc(pension)}</b></span></div>{warn}</div>'
    )


def _report_card(d: dict) -> str:
    s = d["summary"]
    title = f'{s.get("fund_name") or "דוח מקופה"} · {s.get("period") or "תקופה לא ידועה"}'
    balance = _money(s["balance_end"]) if s.get("balance_end") is not None else "לא נמצא"
    parts = [f'<span>יתרה <b>{esc(balance)}</b></span>']
    if s.get("fee_on_savings_pct") is not None:
        fee = _pct(s["fee_on_savings_pct"])
        if s.get("avg_fee_on_savings_pct") is not None:
            fee += f' (ממוצע הקופה {_pct(s["avg_fee_on_savings_pct"])})'
        parts.append(f'<span>דמי ניהול מהצבירה <b>{esc(fee)}</b></span>')
    if s.get("expected_annual_cost_pct") is not None:
        parts.append(f'<span>עלות שנתית צפויה <b>{esc(_pct(s["expected_annual_cost_pct"]))}</b></span>')
    if s.get("track_name"):
        track = s["track_name"] + (f' · {_pct(s["track_return_pct"])}' if s.get("track_return_pct") is not None else "")
        parts.append(f'<span>מסלול <b>{esc(track)}</b></span>')
    notes = []
    if s.get("no_beneficiaries"):
        notes.append("לא נקבעו מוטבים בחשבון")
    if d.get("warnings"):
        notes.append("לבדוק מול הדוח: " + "; ".join(d["warnings"]))
    chips = '<div style="margin-top:8px">' + _chips(notes, "pc-chip-wait") + "</div>" if notes else ""
    return f'<div class="pc-doc"><b>{esc(title)}</b><div class="pc-row">{"".join(parts)}</div>{chips}</div>'


def documents_html(docs: list[dict], prefix: str = "") -> str:
    head = banner_html(prefix)
    title = '<div class="pc-card-head"><h3>המסמכים שלי</h3></div>'
    if not docs:
        return head + (f'<div class="pc-card">{title}<div class="pc-empty">עדיין לא הועלו מסמכים. '
                       'אפשר להעלות תלוש שכר או דוח רבעוני מקופת גמל, השתלמות או פנסיה. '
                       'הקובץ עצמו לא נשמר, רק המספרים שחולצו ממנו.</div></div>')
    slips = [d for d in docs if d.get("doc_type", "payslip") == "payslip"]
    reports = [d for d in docs if d.get("doc_type") == "fund_report"]
    body = ""
    if slips:
        body += '<div class="pc-section">תלושי שכר</div>' + "".join(_slip_card(d) for d in slips[:3])
    if reports:
        body += '<div class="pc-section">דוחות מקופות</div>' + "".join(_report_card(d) for d in reports[:3])
    return head + f'<div class="pc-card">{title}{body}</div>'


def knowledge_html(sources: list[str], error: str | None = None) -> str:
    head = banner_html(f"❌ {error}") if error else ""
    title = '<div class="pc-card-head"><h3>מסמכי ידע</h3></div>'
    if not sources:
        body = '<div class="pc-empty">התיקייה <code>knowledge</code> ריקה. הוסף אליה קבצי .md או .txt עם לוחות עמלות ותקנונים.</div>'
    else:
        body = '<div class="pc-empty">הסוכן עונה על שאלות עמלות ומס רק מתוך המסמכים האלה:</div>' + _chips(sources)
    return head + f'<div class="pc-card">{title}{body}</div>'


def plan_html(plan: SavingsPlan, prefix: str = "") -> str:
    head = banner_html(prefix)
    title = '<div class="pc-card-head"><h3>תוכנית החיסכון החודשית</h3>'
    if plan.is_ready():
        status = '<span class="pc-chip pc-chip-ok">מאושרת</span>'
    elif plan.savings_value:
        status = '<span class="pc-chip pc-chip-wait">ממתינה לאישור</span>'
    else:
        status = '<span class="pc-chip pc-chip-idle">לא נבנתה</span>'
    title += status + "</div>"
    if not plan.savings_value:
        return head + f'<div class="pc-card">{title}<div class="pc-empty">עדיין אין תוכנית. אפשר לבנות אחת בשיחה עם הסוכן או בעריכה ידנית למטה.</div></div>'
    rule = f"{_money(plan.savings_value)} בכל חודש" if plan.savings_mode == "fixed" else f"{plan.savings_value * 100:.0f}% מהנטו"
    buckets = _chips([f"{b.name} {b.share * 100:.0f}%" for b in plan.buckets])
    income = _field("הכנסה נטו אופיינית", _value(_money(plan.monthly_net_income)) if plan.monthly_net_income else _value("—", muted=True))
    reasoning = f'<div class="pc-quote">{esc(plan.rationale)}</div>' if plan.rationale else ""
    return head + (f'<div class="pc-card">{title}<div class="pc-grid">'
                   + _field("כמה מפרישים", _value(rule)) + income
                   + _field("לאן הולכת ההפרשה", buckets, full=True) + "</div>" + reasoning + "</div>")


def _action_text(action: dict) -> str:
    if action["type"] == "transfer":
        return f'העבר <b>{esc(_money(action["amount"]))}</b> אל {esc(action["bucket"])}'
    return f'קנה <b>{esc(_money(action["amount"]))}</b> ב-<span dir="ltr">{esc(action["symbol"])}</span>'


def salary_result_html(result: dict) -> str:
    items = "".join(f"<li>{_action_text(a)}</li>" for a in result["actions"]) or "<li>אין פעולות להצעה החודש</li>"
    notes = [f"הסכום החופשי להוצאות: {_money(result['free_to_spend'])}"]
    if result.get("pension_contributions") or result.get("study_fund_contributions"):
        notes.append(f"הפרשות החודש: פנסיה {_money(result['pension_contributions'])}, השתלמות {_money(result['study_fund_contributions'])}")
    notes.append(f"סך החיסכון החודש כולל הפרשות: {_money(result['total_saved_this_month'])}")
    warn = "".join(f'<div class="pc-banner pc-banner-err">{esc(w)}</div>' for w in result.get("warnings", []))
    if result.get("cap_breached"):
        warn += ('<div class="pc-banner pc-banner-info">נכס בודד חורג מהתקרה שהוגדרה: '
                 + esc(", ".join(result["breaching_symbols"])) + ". ההחלטה אם למכור שלך.</div>")
    return (f'<div class="pc-card"><div class="pc-card-head"><h3>נכנסה משכורת: {esc(result.get("period") or "")}</h3>'
            f'<span class="pc-chip pc-chip-idle">נטו {esc(_money(result["net"]))}</span></div>'
            f'<div class="pc-empty">הצעה לאישור. לא בוצע כלום.</div>{warn}'
            f'<div class="pc-section">מה לעשות עם {esc(_money(result["set_aside"]))}</div><ul class="pc-actions">{items}</ul>'
            f'<div class="pc-empty" style="margin-top:12px">' + "<br>".join(esc(n) for n in notes) + "</div></div>")


def salary_history_html(events: list[dict], prefix: str = "") -> str:
    head = banner_html(prefix)
    if not events:
        return head + '<div class="pc-card"><div class="pc-card-head"><h3>היסטוריה</h3></div><div class="pc-empty">עדיין לא נרשמו משכורות.</div></div>'
    rows = "".join(f'<tr><td>{esc(e.get("period") or "")}</td><td>{_money(e["net"])}</td><td>{_money(e["set_aside"])}</td></tr>' for e in events)
    return head + ('<div class="pc-card"><div class="pc-card-head"><h3>היסטוריה</h3></div>'
                   '<table class="pc-table"><tr><th>חודש</th><th>נטו</th><th>הופרש</th></tr>' + rows + "</table></div>")


# --- מסע המשתמש: שלבים, תמונת מצב והדרכה ---
STAGES = [("intake", "היכרות"), ("picture", "המצב שלי"), ("analysis", "ניתוח והדרכה"), ("monthly", "ניהול חודשי")]


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
        if key != "spouse_monthly_net_income" or profile.spouse_income_required())
    return head + ('<div class="pc-card"><div class="pc-card-head"><h3>התקדמות ההיכרות</h3>' + status + "</div>"
                   f'<div class="pc-chips">{chips}</div></div>')


def intake_result_html(level: str, reasons: list[str], prefix: str = "") -> str:
    head = banner_html(prefix)
    cls = RISK_CLASS.get(level, "pc-chip-idle")
    items = "".join(f"<li>{esc(r)}</li>" for r in reasons)
    return head + ('<div class="pc-card"><div class="pc-card-head"><h3>מה עולה מהראיון</h3>'
                   f'<span class="pc-chip {cls}">רמת סיכון מוצעת: {esc(level)}</span></div>'
                   f'<ul style="margin:0;padding-right:20px;line-height:1.8">{items}</ul>'
                   '<div class="pc-empty">זו הצעה. בשלב הניתוח תאשר או תשנה אותה.</div></div>')


def picture_html(pic: dict, prefix: str = "") -> str:
    head = banner_html(prefix)
    rows = "".join(
        f'<tr><td>{esc(i["label"])}</td><td>{_money(i["value"]) if i["value"] is not None else "—"}</td>'
        f'<td>{_chips([i["source"]]) if i["source"] else ""}</td></tr>' for i in pic["items"])
    total = f'<div class="pc-total">{_money(pic["total"])}</div>' if pic.get("total") is not None else '<div class="pc-empty">עדיין אין נתונים לסיכום.</div>'
    income = pic.get("monthly_net_income")
    metrics = [_field("הכנסה נטו חודשית", _value(_money(income)) if income is not None else _value("—", muted=True))]
    if pic.get("savings_rate") is not None:
        metrics.append(_field("שיעור הפרשה מהנטו", _value(f'{pic["savings_rate"] * 100:.0f}%')))
    if pic.get("emergency_months") is not None:
        metrics.append(_field("חודשי הוצאות מכוסים בכסף נזיל", _value(f'{pic["emergency_months"]:.1f}')))
    grid = f'<div class="pc-grid" style="margin-top:12px">{"".join(metrics)}</div>' if metrics else ""
    gaps = ""
    if pic.get("gaps"):
        gaps = ('<div class="pc-section">מה עוד חסר לתמונה מלאה</div><ul style="margin:0;padding-right:20px;line-height:1.8">'
                + "".join(f"<li>{esc(g)}</li>" for g in pic["gaps"]) + "</ul>")
    return head + ('<div class="pc-card"><div class="pc-card-head"><h3>תמונת המצב שלי</h3>'
                   '<span class="pc-chip pc-chip-idle">שווי כולל ידוע</span></div>' + total +
                   '<table class="pc-table"><tr><th>נכס</th><th>שווי</th><th>מקור</th></tr>' + rows + "</table>" + grid + gaps + "</div>")


def guidance_html(g: Guidance, prefix: str = "") -> str:
    head = banner_html(prefix)
    note = ('<div class="pc-banner pc-banner-info">ניתוח בסיסי שנגזר מהתשובות בקוד. הניתוח של המודל לא היה זמין.</div>'
            if g.source == "fallback" else "")
    risk = ""
    if g.risk_level:
        cls = RISK_CLASS.get(g.risk_level, "pc-chip-idle")
        risk = (f'<div class="pc-field"><span class="pc-label">רמת סיכון מוצעת</span>'
                f'<span><span class="pc-chip {cls}">{esc(g.risk_level)}</span></span>'
                + (f'<span class="pc-empty">{esc(g.risk_reasoning)}</span>' if g.risk_reasoning else "") + "</div>")
    steps = "".join(f'<li><b>{esc(s.title)}</b><span>{esc(s.why)}</span></li>' for s in g.steps)
    steps_html = f'<div class="pc-section">הדרכה: מה לעשות, לפי סדר</div><ul class="pc-steps-list">{steps}</ul>' if steps else ""
    plan = ""
    if g.plan and g.plan.savings_value:
        rule = f"{_money(g.plan.savings_value)} בכל חודש" if g.plan.savings_mode == "fixed" else f"{g.plan.savings_value * 100:.0f}% מהנטו"
        plan = ('<div class="pc-section">תוכנית חודשית מוצעת</div><div class="pc-grid">'
                + _field("כמה מפרישים", _value(rule))
                + _field("לאן", _chips([f"{b.name} {b.share * 100:.0f}%" for b in g.plan.buckets])) + "</div>"
                + (f'<div class="pc-quote">{esc(g.plan.rationale)}</div>' if g.plan.rationale else ""))
    return head + (f'<div class="pc-card"><div class="pc-card-head"><h3>הניתוח שלי</h3></div>{note}'
                   f'<div style="font-size:16px;line-height:1.7;margin-bottom:12px">{esc(g.summary)}</div>{risk}{steps_html}{plan}</div>')