import argparse
import inspect

import gradio as gr

from portfolio_copilot.agent import chat_step, client, MODEL_NAME
from portfolio_copilot.db import Store
from portfolio_copilot.documents import read_document
from portfolio_copilot.proposal import build_proposal, monthly_report
from portfolio_copilot.rag import KnowledgeBase, load_folder
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.situation import load_situation
from portfolio_copilot.ui import (CSS, banner_html, hero_html, intake_progress_html, knowledge_html,
                                  monthly_report_html, profile_html, proposal_html, salary_history_html,
                                  situation_html, stages_html, supported)

USER_NAME = "demo"  # בהמשך אפשר להחליף בהתחברות אמיתית; כל הקוד כבר עובד לפי user_id
NOCHANGE = getattr(gr, "skip", gr.update)
SUGGESTIONS = [
    "מה מצב התיק שלי?",
    "כמה דמי ניהול אני משלם בקופה?",
    "איך כדאי לחלק הפקדה של 2,000 ₪?",
    "כמה דמי ניהול בחשבון מסחר?",
]
INTAKE_GREETING = ("שלום! אני Portfolio Copilot. כמה שאלות קצרות, אחת בכל פעם, כדי שהתוכנית תתאים לך. "
                   "אפשר לתקן כל פרט בהמשך השיחה. נתחיל: מה הגיל שלך?")
INTAKE_DONE_GREETING = "הפרופיל שלך כבר מלא. אפשר לעדכן כאן כל פרט, או לעבור לשלב הבא."


# ---------- מצב ושלבים ----------
def stage_flags(store: Store, user_id: int) -> dict:
    """היכרות ו"המצב שלי" בוצעו כשהפרופיל מלא, ואז נפתח הניהול החודשי. הוא בוצע אחרי דיווח חודשי ראשון."""
    profile_complete = not store.load_profile(user_id).missing_fields()
    return {
        "intake": profile_complete,
        "picture": profile_complete,
        "monthly": profile_complete and bool(store.list_salary_events(user_id)),
    }


# ---------- שיחה עם הסוכן (משותף לשלב 1 ולטאב הצד) ----------
def chat_turn(store: Store, user_id: int, kb, user_input: str, chat_history, profile_state, fetch=None):
    """תור אחד מול הסוכן. הפרופיל מתעדכן רק דרך הכלים שהסוכן מפעיל, ונשמר בסוף התור."""
    chat_history = list(chat_history or [])
    if profile_state is None:
        profile_state = store.load_profile(user_id)
    chat_history.append({"role": "user", "content": user_input})
    try:
        bot_reply, updated_profile = chat_step(chat_history, profile_state, store, user_id, fetch=fetch, kb=kb)
    except Exception as e:
        bot_reply = f"שגיאה בתקשורת עם הסוכן: {e}"
        updated_profile = profile_state
    chat_history.append({"role": "assistant", "content": bot_reply})
    store.save_profile(user_id, updated_profile)
    return chat_history, updated_profile


# ---------- שלב 1: שיחת היכרות ----------
def intake_opening(profile: InvestorProfile) -> list[dict]:
    """ההודעה הראשונה בשיחה. נכתבת בקוד, בלי קריאה למודל."""
    text = INTAKE_DONE_GREETING if not profile.missing_fields() else INTAKE_GREETING
    return [{"role": "assistant", "content": text}]


def intake_panel_html(profile: InvestorProfile) -> str:
    return intake_progress_html(profile) + profile_html(profile)


def make_intake_chat_handler(store: Store, user_id: int, kb=None, fetch=None):
    """שלב 1 לפי תרחיש 2: הסוכן שואל שאלה אחת בכל פעם ושומר את הפרופיל דרך הכלים, עד שהוא מלא."""
    def send(user_input, chat_history, profile_state):
        if not user_input or not user_input.strip():
            profile = profile_state if profile_state is not None else store.load_profile(user_id)
            return ("", chat_history, profile, intake_panel_html(profile), profile_html(profile),
                    stages_html(stage_flags(store, user_id)))
        history, profile = chat_turn(store, user_id, kb, user_input, chat_history, profile_state, fetch)
        return ("", history, profile, intake_panel_html(profile), profile_html(profile),
                stages_html(stage_flags(store, user_id)))

    return send


# ---------- שלב 2: המצב שלי ----------
def make_refresh_handler(store: Store, user_id: int):
    def refresh():
        return situation_html(load_situation(store, user_id)), stages_html(stage_flags(store, user_id))

    return refresh


def make_proposal_handler(store: Store, user_id: int):
    """קבל הצעה: הפרופיל השמור -> build_proposal (קוד בלבד) -> HTML."""
    def show():
        return proposal_html(build_proposal(store.load_profile(user_id)))

    return show


# ---------- ניהול חודשי ----------
AMOUNT_MODES = {"סכום בשקלים": "fixed", "אחוז מהנטו": "percent"}


def make_monthly_handler(store: Store, user_id: int):
    """דיווח חודשי: הפרופיל השמור + מה שהוזן -> monthly_report (קוד בלבד) -> HTML, ונשמר בהיסטוריה."""
    def run(net, pension, study, mode_label, value):
        try:
            report = monthly_report(store.load_profile(user_id), net, pension, study,
                                    AMOUNT_MODES.get(mode_label, ""), value)
        except ValueError as e:
            return salary_history_html(store.list_salary_events(user_id), prefix=f"❌ {e}")
        store.add_salary_event(user_id, report.model_dump(mode="json"))
        return monthly_report_html(report) + salary_history_html(store.list_salary_events(user_id))

    return run


def make_payslip_handler(store: Store, user_id: int):
    """העלאת תלוש (אופציונלי): נקרא בקוד הקיים, נשמר, וממלא את שלושת השדות. אפשר לתקן לפני החישוב."""
    def upload(file):
        if not file:
            return NOCHANGE(), NOCHANGE(), NOCHANGE(), ""
        try:
            doc = read_document(getattr(file, "name", file), client, MODEL_NAME)
        except Exception as e:
            return NOCHANGE(), NOCHANGE(), NOCHANGE(), banner_html(f"❌ {e}")
        store.save_document(user_id, doc)
        s = doc["summary"]
        return (s.get("net_to_bank"), s.get("pension_monthly_total"), s.get("study_fund_monthly_total"),
                banner_html("✅ התלוש נקרא והשדות מולאו. בדוק אותם לפני החישוב."))

    return upload


# ---------- צ'אט: כלי צדדי ----------
def make_chat_handler(store: Store, user_id: int, kb=None):
    def user_message(user_input, chat_history, profile_state):
        if not user_input or not user_input.strip():
            return "", chat_history, profile_state, profile_html(profile_state)
        chat_history, updated_profile = chat_turn(store, user_id, kb, user_input, chat_history, profile_state)
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

    initial_profile = store.load_profile(user_id)

    with gr.Blocks(title="Portfolio Copilot", **supported(gr.Blocks, **blocks_kwargs)) as demo:
        gr.HTML(f"<style>{CSS}</style>" + hero_html())
        stages_display = gr.HTML(stages_html(stage_flags(store, user_id)))
        profile_state = gr.State(initial_profile)

        with gr.Tabs() as tabs:
            # --- 1. היכרות ---
            with gr.Tab("1. היכרות", id="intake"):
                gr.HTML('<div class="pc-card"><div class="pc-card-head"><h3>שיחת היכרות</h3></div><div class="pc-empty">'
                        'הסוכן ישאל שאלה אחת בכל פעם עד שהפרופיל מלא. כל פרט נבדק ונשמר בקוד, '
                        'ורמת הסיכון נקבעת רק אחרי שתאשר אותה.</div></div>')
                with gr.Row(equal_height=False):
                    with gr.Column(scale=5):
                        intake_chatbot = gr.Chatbot(**supported(
                            gr.Chatbot, value=intake_opening(initial_profile), label="שיחת היכרות", height=440, rtl=True))
                        with gr.Row():
                            intake_msg = gr.Textbox(**supported(gr.Textbox, placeholder="כתוב תשובה ולחץ Enter...", show_label=False,
                                                                container=False, scale=6, lines=1, max_lines=4, rtl=True))
                            intake_send = gr.Button("שליחה", variant="primary", scale=1)
                        to_picture_btn = gr.Button("המשך לשלב הבא: המצב שלי", variant="secondary")
                    with gr.Column(scale=3):
                        intake_panel = gr.HTML(intake_panel_html(initial_profile))

            # --- 2. המצב שלי ---
            with gr.Tab("2. המצב שלי", id="picture"):
                gr.HTML('<div class="pc-card"><div class="pc-card-head"><h3>כל המידע במקום אחד</h3></div><div class="pc-empty">'
                        'הנתונים מגיעים משיחת ההיכרות.</div></div>')
                picture_display = gr.HTML(situation_html(load_situation(store, user_id)))
                with gr.Row():
                    refresh_btn = gr.Button("רענן תמונת מצב", variant="secondary")
                    to_monthly_btn = gr.Button("המשך לניהול חודשי", variant="primary")
                proposal_btn = gr.Button("קבל הצעה", variant="primary")
                proposal_display = gr.HTML("")

            # --- 3. ניהול חודשי ---
            with gr.Tab("3. ניהול חודשי", id="monthly"):
                gr.HTML('<div class="pc-card"><div class="pc-card-head"><h3>דיווח חודשי</h3></div><div class="pc-empty">'
                        'הזן את נתוני החודש, או העלה תלוש שימלא אותם. רמת הסיכון והתמהיל נלקחים מהפרופיל.</div></div>')
                payslip_in = gr.File(label="תלוש שכר PDF (לא חובה)", file_types=[".pdf"])
                payslip_status = gr.HTML("")
                with gr.Row():
                    net_in = gr.Number(label="נטו החודש (₪)")
                    pension_m_in = gr.Number(label="הפקדה לפנסיה (₪)")
                    study_m_in = gr.Number(label="הפקדה להשתלמות (₪)")
                with gr.Row():
                    amount_mode_in = gr.Radio(list(AMOUNT_MODES), value="סכום בשקלים", label="כמה להשקיע החודש")
                    amount_in = gr.Number(label="סכום בשקלים, או אחוז מהנטו (למשל 25)")
                salary_btn = gr.Button("חשב חלוקה", variant="primary")
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
        intake_chat = make_intake_chat_handler(store, user_id, kb)
        intake_outputs = [intake_msg, intake_chatbot, profile_state, intake_panel, profile_display, stages_display]
        intake_send.click(fn=intake_chat, inputs=[intake_msg, intake_chatbot, profile_state], outputs=intake_outputs)
        intake_msg.submit(fn=intake_chat, inputs=[intake_msg, intake_chatbot, profile_state], outputs=intake_outputs)
        refresh = make_refresh_handler(store, user_id)
        to_picture_btn.click(fn=lambda: gr.Tabs(selected="picture"), inputs=None, outputs=tabs).then(
            fn=refresh, inputs=None, outputs=[picture_display, stages_display])
        refresh_btn.click(fn=refresh, inputs=None, outputs=[picture_display, stages_display])
        proposal_btn.click(fn=make_proposal_handler(store, user_id), inputs=None, outputs=proposal_display)
        to_monthly_btn.click(fn=lambda: gr.Tabs(selected="monthly"), inputs=None, outputs=tabs)
        salary_btn.click(fn=make_monthly_handler(store, user_id),
                         inputs=[net_in, pension_m_in, study_m_in, amount_mode_in, amount_in], outputs=salary_display)
        payslip_in.upload(fn=make_payslip_handler(store, user_id), inputs=payslip_in,
                          outputs=[net_in, pension_m_in, study_m_in, payslip_status])

        chat = make_chat_handler(store, user_id, kb)
        chat_outputs = [msg_input, chatbot, profile_state, profile_display]
        send_btn.click(fn=chat, inputs=[msg_input, chatbot, profile_state], outputs=chat_outputs)
        msg_input.submit(fn=chat, inputs=[msg_input, chatbot, profile_state], outputs=chat_outputs)
        for button, text in zip(suggestion_buttons, SUGGESTIONS):
            button.click(fn=lambda t=text: t, inputs=None, outputs=msg_input)
        clear_btn.click(fn=lambda: [], inputs=None, outputs=chatbot)

    return demo, supported(gr.Blocks.launch, inbrowser=True, **launch_kwargs)

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portfolio Copilot")
    parser.add_argument("--fresh", action="store_true",
                        help="מסד נתונים בזיכרון בלבד: כל הרצה מתחילה נקייה ושום דבר לא נשמר ב-data/portfolio.db")
    return parser.parse_args(argv)


def open_store(fresh: bool) -> Store:
    """עם --fresh: מסד בזיכרון שנעלם בסוף ההרצה. בלי: הקובץ הרגיל data/portfolio.db."""
    return Store(":memory:") if fresh else Store()


def main(argv=None):
    args = parse_args(argv)
    store = open_store(args.fresh)
    if args.fresh:
        print("[app] --fresh: מסד נתונים בזיכרון. שום דבר מההרצה הזו לא יישמר.")
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