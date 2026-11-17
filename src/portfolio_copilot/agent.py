import datetime
import os
import json
import re
import time
from dotenv import load_dotenv
from openai import OpenAI
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.agent_tools import PROFILE_TOOLS, run_profile_tool, run_tool, tool_specs

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    timeout=30,
    max_retries=2,
)

MODEL_NAME = os.getenv("MODEL_NAME") or "models/gemini-3.5-flash-lite"
MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """אתה Portfolio Copilot – מתכנן ומאפיין פיננסי אישי, בפרויקט אקדמי בקורס מבוא לבינה מלאכותית.
אתה לא יועץ השקעות או פנסיה מורשה, ואתה לא מציג את עצמך ככזה. מותר להזכיר זאת בקצרה כשמתאים.
תפקידך לנהל שיחה אמפתית ומקצועית בעברית כדי לבנות תמונת מצב פיננסית של המשקיע.

אתה מתאים את השפה ואת הניתוח לכל אדם:
- נער/ילד (למשל בן 13 עם מתנת בר מצווה): שפה פשוטה ומעודדת, הסבר על צמיחה לטווח ארוך, הבנה שאין הוצאות שוטפות ולכן אפשר אופק ארוך.
- סטודנט / צעיר: התחשבות בתקציב שוטף, קרן חירום (קרן כספית) לצד השקעה חודשית קטנה ועקבית.
- משפחה צעירה: איזון בין מטרות טווח בינוני (דירה/שדרוג) לטווח ארוך, קרנות השתלמות וחיסכון לילדים.
- לקראת פרישה / פנסיונר: שפה מכבדת, שמירת ערך הקרן, תזרים חודשי יציב, שמרנות ביחס לתנודתיות, והיבטי מס משיכה.

עקרונות השיחה:
1. אל תחקור כמו טופס. שאל שאלה אחת בלבד בכל תור.
2. תהיה פרואקטיבי: אם המשתמש משתף גיל ומצב, הצע רמת סיכון מנומקת (שמרני / מאוזן / אגרסיבי) ומכשירים מתאימים.
3. רמת הסיכון היא הצעה בלבד. אחרי שהצעת אותה, שאל את המשתמש אם היא מתאימה לו.
   risk_confirmed=true רק אם המשתמש אישר במפורש בהודעה האחרונה, או שבחר בעצמו רמת סיכון אחרת.
4. אם המשתמש אומר שהוא לא מוכר נכס מסוים, קרא ל-add_restriction עם הסימול. אל תמחק מגבלות קיימות.
5. אל תמציא מספרים שהמשתמש לא נתן.

בניית הפרופיל:
- בכל פעם שהמשתמש מוסר פרט על עצמו, קרא ל-update_profile עם השדות שאמר, לפני שאתה עונה.
- אם שדה הגיע ב-rejected, הסבר בקצרה למה ובקש אותו שוב.
- אם complete=false, שאל שאלה אחת בלבד, על השדה שב-next_field. אם complete=true, אל תשאל עוד שאלות פרופיל.
- אם המשתמש אומר שהוא לא יודע, העבר את השדה ב-unknown_fields. אם הוא אומר שאין לו (למשל אין חובות), העבר אותו
  ב-none_fields. אל תמציא מספר ואל תכתוב 0 בעצמך. שדה כזה נרשם ולא תישאל עליו שוב.

כלים שעומדים לרשותך:
- update_profile: שמירת פרטי פרופיל, עם בדיקה בקוד. מחזיר accepted, rejected, missing, next_field ו-complete.
- add_restriction: שמירת נכס שהמשתמש לא מוכר. נאכף בקוד בכל חישוב, ומחזיר ב-replan הצעה מחושבת מחדש אם אפשר.
- get_portfolio: ההחזקות של המשתמש עם מחירים, שווי ומשקל. קרא לו כשהמשתמש שואל על התיק שלו או לפני שאתה מדבר על ריכוז.
- plan_deposit: הצעה להשקעה לפי רמת הסיכון שאושרה: חלוקת הפקדה, ואם המשתמש ביקש או הסכים לשקול מכירה (allow_sell=true) גם הצעות מכירה.
  נכסים ששמרת עם add_restriction לא יוצעו למכירה אוטומטית. קרא לו רק אחרי שהמשתמש אישר את רמת הסיכון.
- get_documents: נתונים ממסמכים שהמשתמש העלה: תלושי שכר (נטו, הפרשות לפנסיה, מס שולי) ודוחות רבעוניים מקופות
  גמל, השתלמות ופנסיה (יתרה, דמי ניהול מול ממוצע הקופה, מסלול ותשואה). קרא לו כשמדברים על הכנסה,
  על חיסכון פנסיוני, או לפני שאתה מציע כמה אפשר להפקיד בחודש. אם יש warnings, ציין שכדאי לאמת את המספרים מול התלוש.
  כששואלים על דמי הניהול של המשתמש, הצג את המספרים מדוח הקופה (fund_reports) והשווה לממוצע הקופה אם קיים.
  סכום הפקדה חודשי הוא החלטה של המשתמש: אפשר להציע טווח לפי הנטו, ולשאול אותו כמה מתאים לו.
- search_documents: חיפוש במסמכי הידע (עמלות, דמי ניהול, תקנונים, כללי מס). קרא לו לכל שאלה על עלויות, מס או כללי קרנות וקופות.
- propose_plan: שמירת תוכנית החיסכון החודשית של המשתמש. אחרי שהפרופיל אושר, בנה תוכנית שמתאימה לאדם הזה:
  כמה נכנס לו נטו, כמה הוא יכול להפריש (סכום קבוע או אחוז מהנטו), ואיך לחלק את ההפרשה בין כסף נזיל (קרן חירום, מטרה קרובה)
  להשקעות. הצע את התוכנית ושאל אם היא מתאימה. user_confirmed=true רק אם המשתמש אישר במפורש.
  אל תקבע סכום הפרשה שהמשתמש לא אמר או אישר. אדם עם הכנסה גבוהה והרבה פנאי פיננסי לא דומה לנער שמרוויח מעט.
- salary_received: כשהמשתמש אומר שנכנסה משכורת. מחזיר רשימת פעולות מוצעות לאישור לפי התוכנית. אפשר בלי סכומים, והם יילקחו מהתלוש האחרון.
כללי שימוש בכלים:
- כל מספר שאתה מציג מהתיק או מהחלוקה חייב להגיע מתוצאת כלי. אל תחשב ואל תנחש בעצמך.
- אם הכלי מחזיר שגיאה, הסבר למשתמש בפשטות מה חסר.
- אם cap_breached=true, הסבר שנכס אחד חורג מהתקרה שהוגדרה, שההפקדות החדשות יורידו את משקלו בהדרגה בלי למכור, ושההחלטה אם למכור שייכת למשתמש.
- הצג את התוצאה כמידע להחלטה ולא כהוראה לביצוע.
- על שאלות עלות ומס ענה רק מתוך הקטעים ש-search_documents החזיר, וציין את שם המסמך כמקור.
  אם הקטעים לא עונים על השאלה, אמור שלא נמצא מידע במסמכים. אל תנחש מספרים ואל תשלים מהידע הכללי שלך.

פורמט התשובה:
- ענה למשתמש בטקסט רגיל בעברית, בלי JSON.
- הפרופיל מתעדכן אך ורק דרך הכלים update_profile ו-add_restriction. מה שלא נשמר דרכם לא נשמר בכלל.
"""


def extract_json(text: str) -> dict:
    """מחלץ אובייקט JSON מהתשובה. strict=False מאפשר ירידות שורה גולמיות בתוך מחרוזות,
    דבר שמודלים עושים הרבה ושמפיל את הפענוח הרגיל."""
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text, strict=False)


def salvage_reply(text: str) -> str | None:
    """אם ה-JSON שבור, מנסה לשלוף לפחות את שדה reply כדי שהמשתמש יקבל תשובה."""
    match = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', text or "", re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(f'"{match.group(1)}"', strict=False)
    except json.JSONDecodeError:
        return match.group(1).replace("\\n", "\n").replace('\\"', '"')


FALLBACK_REPLY = "לא הצלחתי לעבד את התשובה, אפשר לנסח שוב?"


def final_reply_text(raw: str | None) -> str:
    """התשובה הסופית של המודל היא טקסט רגיל ומוצגת כמו שהיא.
    אם המודל בכל זאת החזיר JSON עם reply, מחלצים רק את reply. שדות אחרים (כמו profile) לא נקראים."""
    text = (raw or "").strip()
    if not text:
        return FALLBACK_REPLY
    if '"reply"' in text:
        try:
            data = extract_json(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("reply"), str) and data["reply"].strip():
            return data["reply"]
        salvaged = salvage_reply(text)
        if salvaged and salvaged.strip():
            return salvaged
    if text.startswith(("{", "[")) or (text.startswith("```") and "{" in text):
        print("[agent] התשובה נראית כמו JSON בלי reply. תשובת המודל:\n", text[:1200])
        return FALLBACK_REPLY
    return text


REPAIR_PROMPT = """קיבלת את ההודעה האחרונה של משתמש ואת תשובת סוכן פיננסי שלא הגיעה כ-JSON תקין.
החזר אך ורק אובייקט JSON תקין אחד במבנה {"reply": "...", "profile": {...}}.
שמור ב-reply את תשובת הסוכן כמו שהיא, בלי לשנות.
ב-profile מלא רק שדות שהמשתמש אמר במפורש בהודעה האחרונה (age, life_stage, initial_amount, monthly_deposit,
needs_cashflow, investment_goal, investment_horizon_years, restrictions), וגם recommended_risk_level אם הסוכן הציע.
אל תמציא. שדה לא ידוע הוא null. risk_confirmed הוא false אלא אם המשתמש אישר במפורש."""


def repair_to_json(raw: str, history: list[dict]) -> dict | None:
    """קריאה שנייה וקצרה שממירה תשובה שבורה (או טקסט חופשי) ל-JSON תקין. מנסים פעם אחת בלבד."""
    last_user = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            messages=[
                {"role": "system", "content": REPAIR_PROMPT},
                {"role": "user", "content": json.dumps({"last_user_message": last_user, "agent_text": raw}, ensure_ascii=False)},
            ],
        )
        data = extract_json(response.choices[0].message.content or "")
        return data if isinstance(data, dict) and "reply" in data else None
    except Exception:
        return None


def chat_step(messages_history: list[dict], current_profile: InvestorProfile,
              store=None, user_id: int | None = None, fetch=None, kb=None) -> tuple[str, InvestorProfile]:
    """מריץ תור שיחה. אם יש store ו-user_id, הסוכן יכול להפעיל כלים.

    כלי פרופיל (update_profile, add_restriction) מעדכנים את הפרופיל כבר בתוך הלולאה: כלים שרצים
    אחריהם באותו תור רואים את הפרופיל החדש, והוא נשמר מיד ב-store.
    """
    def profile_message(profile: InvestorProfile) -> dict:
        return {"role": "system", "content": f"פרופיל נוכחי שנאסף עד כה:\n{profile.model_dump_json()}"}

    today_line = (f"התאריך היום: {datetime.date.today().isoformat()}. השתמש בו לכל חישוב של כמה שנים נשארו "
                  "עד שנה עתידית, ואל תניח שהשנה היא שנת האימון שלך.")
    prompt_messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n{today_line}"},
        profile_message(current_profile),
    ]
    prompt_messages.extend(messages_history)
    use_tools = store is not None and user_id is not None

    try:
        for round_no in range(MAX_TOOL_ROUNDS + 1):
            kwargs = {"model": MODEL_NAME, "messages": prompt_messages, "temperature": 0.3}
            if use_tools and round_no < MAX_TOOL_ROUNDS:
                kwargs["tools"] = tool_specs(kb is not None)
            started = time.perf_counter()
            response = client.chat.completions.create(**kwargs)
            llm_seconds = time.perf_counter() - started
            message = response.choices[0].message

            if not message.tool_calls:
                print(f"[agent] round {round_no + 1}: LLM {llm_seconds:.2f}s | tools: none (final answer)")
                break

            # מחזירים למודל את בקשת הכלים (כולל שדות נוספים של הספק) ואת התוצאות
            prompt_messages.append(message.model_dump(exclude_none=True))
            tool_timings = []
            for call in message.tool_calls:
                tool_started = time.perf_counter()
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if call.function.name in PROFILE_TOOLS:
                    result, new_profile = run_profile_tool(call.function.name, args, current_profile,
                                                           store, user_id, fetch)
                    if new_profile != current_profile:
                        current_profile = new_profile
                        prompt_messages[1] = profile_message(current_profile)
                        store.save_profile(user_id, current_profile)
                else:
                    result = run_tool(call.function.name, args, store, user_id, current_profile, fetch, kb)
                prompt_messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
                timing = f"{call.function.name} ({time.perf_counter() - tool_started:.2f}s)"
                if call.function.name == "update_profile":
                    timing += f" args={json.dumps(args, ensure_ascii=False)}"
                tool_timings.append(timing)
            print(f"[agent] round {round_no + 1}: LLM {llm_seconds:.2f}s | tools: {', '.join(tool_timings)}")

        # הפרופיל כבר עודכן בכלים. התשובה הסופית היא טקסט בלבד ולא משנה אותו.
        return final_reply_text(message.content), current_profile

    except Exception as e:
        return f"שגיאה בתקשורת עם הסוכן: {e}", current_profile