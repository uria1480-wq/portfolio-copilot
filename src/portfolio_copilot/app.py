import inspect

import gradio as gr

from portfolio_copilot.agent import chat_step, client, MODEL_NAME
from portfolio_copilot.agent_tools import _prices_for
from portfolio_copilot.analysis import LEVELS, analyze
from portfolio_copilot.db import Store
from portfolio_copilot.fund_reports import read_any_document
from portfolio_copilot.intake import (EXPERIENCE_OPTIONS, GOAL_OPTIONS, HORIZON_OPTIONS, MAX_WEIGHT_OPTIONS,
                                      REACTION_OPTIONS, STATUS_OPTIONS, IntakeAnswers, derive_profile,
                                      missing_fields, risk_assessment)
from portfolio_copilot.picture import build_picture
from portfolio_copilot.plan import Bucket, SavingsPlan
from portfolio_copilot.rag import KnowledgeBase, load_folder
from portfolio_copilot.salary import plan_salary
from portfolio_copilot.tools import parse_holdings_csv
from portfolio_copilot.ui import (CSS, banner_html, documents_html, guidance_html, hero_html, holdings_html,
                                  intake_result_html, knowledge_html, picture_html, plan_html, profile_html,
                                  salary_history_html, salary_result_html, stages_html, supported)

USER_NAME = "demo"  # בהמשך אפשר להחליף בהתחברות אמיתית; כל הקוד כבר עובד לפי user_id
NOCHANGE = getattr(gr, "skip", gr.update)
SUGGESTIONS = [
    "מה מצב התיק שלי?",
    "כמה דמי ניהול אני משלם בקופה?",
    "איך כדאי לחלק הפקדה של 2,000 ₪?",
    "כמה דמי ניהול בחשבון מסחר?",
]


# ---------- מצב ושלבים ----------
def load_intake(store: Store, user_id: int) -> IntakeAnswers:
    data = store.load_state(user_id, "intake")
    return IntakeAnswers.model_validate(data) if data else IntakeAnswers()


def stage_flags(store: Store, user_id: int) -> dict:
    a = load_intake(store, user_id)
    has_info = (bool(store.list_documents(user_id)) or bool(store.list_holdings(user_id))
                or any(getattr(a, k) is not None for k in ("pension_value", "study_fund_value", "other_assets")))
    return {
        "intake": not missing_fields(a),
        "picture": has_info,
        "analysis": store.load_state(user_id, "guidance") is not None,
        "monthly": store.load_plan(user_id).is_ready() and store.load_profile(user_id).is_complete(),
    }


def compute_picture(store: Store, user_id: int, fetch=None) -> dict:
    holdings = store.list_holdings(user_id)
    value, errors = None, []
    if holdings:
        prices, errors = _prices_for([h["symbol"] for h in holdings], fetch)
        if not errors:
            value = round(sum(h["quantity"] * prices[h["symbol"]] for h in holdings), 2)
    return build_picture(load_intake(store, user_id), value, store.list_documents(user_id, "fund_report"),
                         store.list_documents(user_id, "payslip"), errors)


# ---------- שלב 1: ראיון ----------
def make_intake_handler(store: Store, user_id: int, fetch=None):
    def save(age, status, income, expenses, can_save, liquid, debt, goals, horizon, reaction, experience, max_weight, restrictions):
        previous = load_intake(store, user_id)
        try:
            answers = IntakeAnswers(
                age=int(age) if age is not None else None, status=status or None, monthly_net_income=income,
                monthly_expenses=expenses, can_save_monthly=can_save, liquid_savings=liquid, monthly_debt_payments=debt,
                goals=list(goals or []), horizon_label=horizon, reaction_label=reaction, experience_label=experience,
                max_weight_label=max_weight, restrictions_text=restrictions or "",
                pension_value=previous.pension_value, study_fund_value=previous.study_fund_value,
                other_assets=previous.other_assets)
        except ValueError:
            return (banner_html("❌ יש ערך לא תקין בטופס. מספרים צריכים להיות חיוביים."), stages_html(stage_flags(store, user_id)),
                    picture_html(compute_picture(store, user_id, fetch)), NOCHANGE())
        store.save_state(user_id, "intake", answers.model_dump())
        missing = missing_fields(answers)
        if missing:
            return (banner_html("❌ חסר מידע בשאלות החובה: " + ", ".join(missing)), stages_html(stage_flags(store, user_id)),
                    picture_html(compute_picture(store, user_id, fetch)), NOCHANGE())
        level, reasons, _ = risk_assessment(answers)
        store.save_profile(user_id, derive_profile(answers))
        return (intake_result_html(level, reasons, prefix="✅ הראיון נשמר. עוברים לשלב הבא."),
                stages_html(stage_flags(store, user_id)), picture_html(compute_picture(store, user_id, fetch)),
                gr.Tabs(selected="picture"))

    return save


# ---------- שלב 2: המצב שלי ----------
def make_upload_handler(store: Store, user_id: int):
    def upload(file):
        if not file:
            return holdings_html(store.list_holdings(user_id))
        path = getattr(file, "name", file)
        try:
            with open(path, encoding="utf-8-sig") as f:
                rows = parse_holdings_csv(f.read())
        except (ValueError, OSError, UnicodeDecodeError) as e:
            return holdings_html(store.list_holdings(user_id), prefix=f"❌ {e}")
        new_symbols = {r["symbol"] for r in rows}
        for h in store.list_holdings(user_id):  # הקובץ מחליף את התיק הקיים
            if h["symbol"] not in new_symbols:
                store.delete_holding(user_id, h["symbol"])
        for r in rows:
            store.upsert_holding(user_id, r["symbol"], r["quantity"], r["avg_cost"])
        return holdings_html(store.list_holdings(user_id), prefix=f"✅ נטענו {len(rows)} החזקות. הקובץ מחליף את התיק הקיים.")

    return upload


def make_document_handler(store: Store, user_id: int):
    def upload(file):
        if not file:
            return documents_html(store.list_documents(user_id))
        path = getattr(file, "name", file)
        try:
            doc = read_any_document(path, client, MODEL_NAME)
        except Exception as e:
            return documents_html(store.list_documents(user_id), prefix=f"❌ {e}")
        store.save_document(user_id, doc)
        return documents_html(store.list_documents(user_id), prefix="✅ המסמך נקרא. הקובץ עצמו לא נשמר, רק הנתונים.")

    return upload


def make_assets_handler(store: Store, user_id: int, fetch=None):
    def save(pension, study, other):
        try:
            answers = load_intake(store, user_id).model_copy(update={
                "pension_value": pension, "study_fund_value": study, "other_assets": other})
            IntakeAnswers.model_validate(answers.model_dump())
        except ValueError:
            return picture_html(compute_picture(store, user_id, fetch), prefix="❌ הערכים צריכים להיות חיוביים"), NOCHANGE()
        store.save_state(user_id, "intake", answers.model_dump())
        return picture_html(compute_picture(store, user_id, fetch), prefix="✅ הערכים נשמרו"), stages_html(stage_flags(store, user_id))

    return save


def make_refresh_handler(store: Store, user_id: int, fetch=None):
    def refresh():
        return picture_html(compute_picture(store, user_id, fetch)), stages_html(stage_flags(store, user_id))

    return refresh


# ---------- שלב 3: ניתוח והדרכה ----------
def make_analysis_handler(store: Store, user_id: int, llm_client, model: str, fetch=None):
    def run():
        answers = load_intake(store, user_id)
        missing = missing_fields(answers)
        if missing:
            return (banner_html("❌ השלם קודם את הראיון. חסר: " + ", ".join(missing)),
                    NOCHANGE(), NOCHANGE(), NOCHANGE(), NOCHANGE(), NOCHANGE(), NOCHANGE(), NOCHANGE())
        level, reasons, _ = risk_assessment(answers)
        guidance = analyze(answers, compute_picture(store, user_id, fetch), level, reasons, llm_client, model)
        store.save_state(user_id, "guidance", guidance.model_dump(mode="json"))
        plan = guidance.plan
        if plan:
            store.save_plan(user_id, plan)  # טיוטה, עדיין לא מאושרת
        risk = guidance.risk_level or level
        if plan:
            percent = plan.savings_mode == "percent"
            editor = ("אחוז מהנטו" if percent else "סכום קבוע בשקלים",
                      plan.savings_value * 100 if percent else plan.savings_value,
                      round(sum(b.share for b in plan.buckets if b.kind == "cash") * 100),
                      plan.monthly_net_income)
        else:
            editor = (NOCHANGE(), NOCHANGE(), NOCHANGE(), NOCHANGE())
        return (guidance_html(guidance), risk, *editor, plan_html(store.load_plan(user_id)),
                stages_html(stage_flags(store, user_id)))

    return run


def make_confirm_handler(store: Store, user_id: int):
    def confirm(risk, mode_label, value, cash_pct, income):
        def fail(message):
            return (banner_html("❌ " + message), NOCHANGE(), NOCHANGE(), NOCHANGE(), NOCHANGE(), NOCHANGE())

        answers = load_intake(store, user_id)
        if missing_fields(answers):
            return fail("השלם קודם את הראיון")
        if risk not in LEVELS:
            return fail("בחר רמת סיכון")
        if not value or value <= 0:
            return fail("הזן סכום או אחוז הפרשה")
        try:
            cash = min(max((cash_pct or 0) / 100, 0), 1)
            guidance = store.load_state(user_id, "guidance") or {}
            rationale = ((guidance.get("plan") or {}).get("rationale")) or None
            plan = SavingsPlan(
                monthly_net_income=income or None,
                savings_mode="percent" if str(mode_label).startswith("אחוז") else "fixed",
                savings_value=float(value),
                buckets=[Bucket(name="כסף נזיל / קרן חירום", kind="cash", share=cash),
                         Bucket(name="השקעות", kind="invest", share=1 - cash)],
                rationale=rationale, confirmed=True)
        except ValueError as e:
            return fail(str(e))
        profile = derive_profile(answers).model_copy(update={"recommended_risk_level": risk, "risk_confirmed": True})
        store.save_profile(user_id, profile)
        store.save_plan(user_id, plan)
        return (banner_html("✅ התוכנית אושרה. עוברים לניהול החודשי."), plan_html(plan),
                stages_html(stage_flags(store, user_id)), gr.Tabs(selected="monthly"), profile, profile_html(profile))

    return confirm


# ---------- שלב 4: ניהול חודשי ----------
def make_prefill_handler(store: Store, user_id: int):
    def prefill():
        slips = store.list_documents(user_id, "payslip")
        if not slips:
            return None, None, None
        s = slips[0]["summary"]
        return s.get("net_to_bank"), s.get("pension_monthly_total"), s.get("study_fund_monthly_total")

    return prefill


def make_salary_handler(store: Store, user_id: int, fetch=None):
    def run(net, pension, study):
        try:
            if not net or net <= 0:
                raise ValueError("הזן כמה נכנס נטו לחשבון הבנק")
            holdings = store.list_holdings(user_id)
            prices, errors = _prices_for([h["symbol"] for h in holdings], fetch)
            if errors:
                raise ValueError(f"לא נמצאו מחירים עבור: {', '.join(errors)}")
            result = plan_salary(store.load_profile(user_id), store.load_plan(user_id), holdings, prices,
                                 float(net), float(pension or 0), float(study or 0))
            store.add_salary_event(user_id, result)
        except ValueError as e:
            return salary_history_html(store.list_salary_events(user_id), prefix=f"❌ {e}")
        return salary_result_html(result) + salary_history_html(store.list_salary_events(user_id))

    return run


# ---------- צ'אט: כלי צדדי ----------
def make_chat_handler(store: Store, user_id: int, kb=None):
    def user_message(user_input, chat_history, profile_state):
        if not user_input or not user_input.strip():
            return "", chat_history, profile_state, profile_html(profile_state)
        if chat_history is None:
            chat_history = []
        if profile_state is None:
            profile_state = store.load_profile(user_id)
        chat_history.append({"role": "user", "content": user_input})
        try:
            bot_reply, updated_profile = chat_step(chat_history, profile_state, store, user_id, kb=kb)
        except Exception as e:
            bot_reply = f"שגיאה בתקשורת עם הסוכן: {e}"
            updated_profile = profile_state
        chat_history.append({"role": "assistant", "content": bot_reply})
        store.save_profile(user_id, updated_profile)
        return "", chat_history, updated_profile, profile_html(updated_profile)

    return user_message


# ---------- בניית הממשק ----------
def _choice(value, choices):
    return value if value in choices else None


def build_demo(store: Store, user_id: int, kb=None, kb_error=None):
    """בונה את הממשק. מחזיר (demo, launch_kwargs)."""
    theme = gr.themes.Soft(primary_hue="indigo", neutral_hue="slate",
                           font=[gr.themes.GoogleFont("Heebo"), "Segoe UI", "Arial", "sans-serif"])
    style = {"theme": theme, "css": CSS}
    if "css" in inspect.signature(gr.Blocks.launch).parameters:
        blocks_kwargs, launch_kwargs = {}, dict(style)
    else:
        blocks_kwargs, launch_kwargs = dict(style), {}

    a = load_intake(store, user_id)
    initial_profile = store.load_profile(user_id)
    guidance_saved = store.load_state(user_id, "guidance")

    with gr.Blocks(title="Portfolio Copilot", **supported(gr.Blocks, **blocks_kwargs)) as demo:
        gr.HTML(f"<style>{CSS}</style>" + hero_html())
        stages_display = gr.HTML(stages_html(stage_flags(store, user_id)))
        profile_state = gr.State(initial_profile)

        with gr.Tabs() as tabs:
            # --- 1. היכרות ---
            with gr.Tab("1. היכרות", id="intake"):
                gr.HTML('<div class="pc-card"><div class="pc-card-head"><h3>ראיון היכרות</h3></div><div class="pc-empty">'
                        'כמה שאלות כדי שהתוכנית תתאים בדיוק לך. אפשר לחזור ולעדכן בכל שלב.</div></div>')
                gr.HTML('<div class="pc-section">עליך</div>')
                with gr.Row():
                    age_in = gr.Number(**supported(gr.Number, label="גיל", value=a.age, precision=0, minimum=0, maximum=120))
                    status_in = gr.Dropdown(STATUS_OPTIONS, label="מצב תעסוקתי", value=_choice(a.status, STATUS_OPTIONS))
                gr.HTML('<div class="pc-section">כסף</div>')
                with gr.Row():
                    income_in = gr.Number(label="הכנסה נטו חודשית (₪)", value=a.monthly_net_income)
                    expenses_in = gr.Number(label="הוצאות חודשיות קבועות (₪)", value=a.monthly_expenses)
                    save_in = gr.Number(label="כמה אפשר להפריש בחודש (₪)", value=a.can_save_monthly)
                with gr.Row():
                    liquid_in = gr.Number(label="כסף נזיל וחסכונות בבנק (₪)", value=a.liquid_savings)
                    debt_in = gr.Number(label="החזרי הלוואות או משכנתא בחודש (₪)", value=a.monthly_debt_payments)
                gr.HTML('<div class="pc-section">יעדים</div>')
                goals_in = gr.CheckboxGroup(GOAL_OPTIONS, label="מה חשוב לך להשיג", value=[g for g in a.goals if g in GOAL_OPTIONS])
                horizon_in = gr.Radio(list(HORIZON_OPTIONS), label="באיזה אופק זמן אתה חושב על ההשקעות", value=_choice(a.horizon_label, HORIZON_OPTIONS))
                gr.HTML('<div class="pc-section">גישה לסיכון</div>')
                reaction_in = gr.Radio(list(REACTION_OPTIONS), label="אם התיק שלך יורד ב-20% בכמה חודשים, מה תעשה?", value=_choice(a.reaction_label, REACTION_OPTIONS))
                experience_in = gr.Radio(list(EXPERIENCE_OPTIONS), label="ניסיון בהשקעות", value=_choice(a.experience_label, EXPERIENCE_OPTIONS))
                max_weight_in = gr.Radio(list(MAX_WEIGHT_OPTIONS), label="כמה מהתיק מותר שיהיה בנכס בודד", value=_choice(a.max_weight_label, MAX_WEIGHT_OPTIONS) or "עד 20%")
                restrictions_in = gr.Textbox(label="נכסים שאתה לא מוכר או לא רוצה (אחד בכל שורה)", lines=2, value=a.restrictions_text)
                intake_btn = gr.Button("שמור והמשך", variant="primary")
                intake_status = gr.HTML("")

            # --- 2. המצב שלי ---
            with gr.Tab("2. המצב שלי", id="picture"):
                gr.HTML('<div class="pc-card"><div class="pc-card-head"><h3>כל המידע במקום אחד</h3></div><div class="pc-empty">'
                        'צרף תלוש שכר, דוחות רבעוניים מקופות (פנסיה, השתלמות, גמל) וקובץ החזקות, או הזן שווי ידנית. '
                        'הקבצים עצמם לא נשמרים, רק המספרים.</div></div>')
                with gr.Row():
                    with gr.Column():
                        doc_input = gr.File(label="מסמך PDF: תלוש שכר או דוח רבעוני מקופה", file_types=[".pdf"])
                        docs_display = gr.HTML(documents_html(store.list_documents(user_id)))
                    with gr.Column():
                        file_input = gr.File(label="החזקות (CSV: symbol, quantity, avg_cost)", file_types=[".csv"])
                        holdings_display = gr.HTML(holdings_html(store.list_holdings(user_id)))
                with gr.Accordion("הזנה ידנית של שווי, אם אין מסמך", open=False):
                    with gr.Row():
                        pension_in = gr.Number(label="שווי קרן פנסיה (₪)", value=a.pension_value)
                        study_in = gr.Number(label="שווי קרן השתלמות (₪)", value=a.study_fund_value)
                        other_in = gr.Number(label="נכסים אחרים (₪)", value=a.other_assets)
                    assets_btn = gr.Button("שמור ערכים")
                picture_display = gr.HTML(picture_html(compute_picture(store, user_id)))
                with gr.Row():
                    refresh_btn = gr.Button("רענן תמונת מצב", variant="secondary")
                    to_analysis_btn = gr.Button("המשך לניתוח והדרכה", variant="primary")

            # --- 3. ניתוח והדרכה ---
            with gr.Tab("3. ניתוח והדרכה", id="analysis"):
                analyze_btn = gr.Button("נתח את המצב שלי", variant="primary")
                guidance_display = gr.HTML("")
                gr.HTML('<div class="pc-section">אישור התוכנית (אפשר לשנות לפני האישור)</div>')
                risk_in = gr.Radio(list(LEVELS), label="רמת סיכון", value=initial_profile.recommended_risk_level)
                with gr.Row():
                    mode_in = gr.Radio(["סכום קבוע בשקלים", "אחוז מהנטו"], value="סכום קבוע בשקלים", label="איך מחשבים כמה להפריש")
                    value_in = gr.Number(label="סכום בשקלים, או אחוז (למשל 25)")
                with gr.Row():
                    cash_in = gr.Slider(0, 100, value=30, step=5, label="כמה אחוזים מההפרשה נשארים כסף נזיל או קרן חירום")
                    plan_income_in = gr.Number(label="הכנסה נטו חודשית אופיינית (לא חובה)")
                confirm_btn = gr.Button("אשר והתחל ניהול חודשי", variant="primary")
                confirm_status = gr.HTML("")

            # --- 4. ניהול חודשי ---
            with gr.Tab("4. ניהול חודשי", id="monthly"):
                plan_display = gr.HTML(plan_html(store.load_plan(user_id)))
                gr.HTML('<div class="pc-section">נכנסה משכורת</div>')
                with gr.Row():
                    net_in = gr.Number(label="נטו שנכנס לבנק (₪)")
                    pension_m_in = gr.Number(label="הופרש לפנסיה (₪)")
                    study_m_in = gr.Number(label="הופרש להשתלמות (₪)")
                with gr.Row():
                    fill_btn = gr.Button("מלא מהתלוש האחרון", size="sm", variant="secondary")
                    salary_btn = gr.Button("נכנסה משכורת", variant="primary")
                salary_display = gr.HTML(salary_history_html(store.list_salary_events(user_id)))

            # --- שאל את הסוכן ---
            with gr.Tab("שאל את הסוכן", id="chat"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=5):
                        chatbot = gr.Chatbot(**supported(
                            gr.Chatbot, label="שיחה", height=480, rtl=True,
                            placeholder="<strong>שאלות על התיק, המסמכים או עלויות</strong><br>הסוכן מכיר את הפרופיל והנתונים שלך."))
                        with gr.Row():
                            suggestion_buttons = [gr.Button(t, size="sm", variant="secondary", elem_classes="pc-suggest") for t in SUGGESTIONS]
                        with gr.Row():
                            msg_input = gr.Textbox(**supported(gr.Textbox, placeholder="כתוב כאן הודעה ולחץ Enter...", show_label=False,
                                                               container=False, scale=6, lines=1, max_lines=4, rtl=True))
                            send_btn = gr.Button("שליחה", variant="primary", scale=1)
                        clear_btn = gr.Button("שיחה חדשה", size="sm", variant="secondary")
                    with gr.Column(scale=3):
                        profile_display = gr.HTML(profile_html(initial_profile))
                        gr.HTML(knowledge_html(kb.sources() if kb is not None else [], kb_error))

        # --- חיווט ---
        intake_btn.click(fn=make_intake_handler(store, user_id),
                         inputs=[age_in, status_in, income_in, expenses_in, save_in, liquid_in, debt_in, goals_in,
                                 horizon_in, reaction_in, experience_in, max_weight_in, restrictions_in],
                         outputs=[intake_status, stages_display, picture_display, tabs])
        refresh = make_refresh_handler(store, user_id)
        file_input.upload(fn=make_upload_handler(store, user_id), inputs=file_input, outputs=holdings_display).then(
            fn=refresh, inputs=None, outputs=[picture_display, stages_display])
        doc_input.upload(fn=make_document_handler(store, user_id), inputs=doc_input, outputs=docs_display).then(
            fn=refresh, inputs=None, outputs=[picture_display, stages_display])
        assets_btn.click(fn=make_assets_handler(store, user_id), inputs=[pension_in, study_in, other_in],
                         outputs=[picture_display, stages_display])
        refresh_btn.click(fn=refresh, inputs=None, outputs=[picture_display, stages_display])
        to_analysis_btn.click(fn=lambda: gr.Tabs(selected="analysis"), inputs=None, outputs=tabs)
        analyze_btn.click(fn=make_analysis_handler(store, user_id, client, MODEL_NAME), inputs=None,
                          outputs=[guidance_display, risk_in, mode_in, value_in, cash_in, plan_income_in, plan_display, stages_display])
        confirm_btn.click(fn=make_confirm_handler(store, user_id),
                          inputs=[risk_in, mode_in, value_in, cash_in, plan_income_in],
                          outputs=[confirm_status, plan_display, stages_display, tabs, profile_state, profile_display])
        fill_btn.click(fn=make_prefill_handler(store, user_id), inputs=None, outputs=[net_in, pension_m_in, study_m_in])
        salary_btn.click(fn=make_salary_handler(store, user_id), inputs=[net_in, pension_m_in, study_m_in], outputs=salary_display)

        chat = make_chat_handler(store, user_id, kb)
        chat_outputs = [msg_input, chatbot, profile_state, profile_display]
        send_btn.click(fn=chat, inputs=[msg_input, chatbot, profile_state], outputs=chat_outputs)
        msg_input.submit(fn=chat, inputs=[msg_input, chatbot, profile_state], outputs=chat_outputs)
        for button, text in zip(suggestion_buttons, SUGGESTIONS):
            button.click(fn=lambda t=text: t, inputs=None, outputs=msg_input)
        clear_btn.click(fn=lambda: [], inputs=None, outputs=chatbot)

    return demo, supported(gr.Blocks.launch, inbrowser=True, **launch_kwargs)

def main():
    store = Store()
    user_id = store.get_or_create_user(USER_NAME)

    kb, kb_error = None, None
    try:
        kb = KnowledgeBase("data/chroma")
        load_folder(kb, "knowledge")
    except Exception as e:  # האפליקציה ממשיכה לעבוד גם אם הטמעת המסמכים נכשלה
        kb_error = str(e)

    demo, launch_kwargs = build_demo(store, user_id, kb, kb_error)
    launch_kwargs.update(share=True, auth=("family", "u12345"))
    demo.launch(**launch_kwargs)


if __name__ == "__main__":
    main()