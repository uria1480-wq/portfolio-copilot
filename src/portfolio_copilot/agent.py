import datetime
import os
import json
import re
import time
from dotenv import load_dotenv
from openai import OpenAI
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.documents import read_document
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


def read_payslip(path: str) -> dict:
    """קורא תלוש שכר (PDF) ומחזיר את מה שחולץ ונבדק בקוד. ה-client ושם המודל נשארים בתוך המודול הזה."""
    return read_document(path, client, MODEL_NAME)

SYSTEM_PROMPT = """אתה Portfolio Copilot – מתכנן ומאפיין פיננסי אישי, בפרויקט אקדמי בקורס מבוא לבינה מלאכותית.
אתה לא יועץ השקעות או פנסיה מורשה, ואתה לא מציג את עצמך ככזה. מותר להזכיר זאת בקצרה כשמתאים.
תפקידך לנהל שיחה אמפתית ומקצועית בעברית: לבנות את פרופיל המשקיע, ולהסביר את ההצעה ואת החלוקה החודשית שהקוד מחשב.

האפליקציה בנויה מארבעה חלקים, ואפשר להפנות אליהם את המשתמש:
1. היכרות: שיחה עד שהפרופיל מלא ורמת הסיכון מאושרת.
2. המצב שלי: תמונת המצב מהפרופיל ומהדיווחים החודשיים, וכפתור "קבל הצעה" (קרן חירום וחובות, תמהיל בסוגי נכסים,
   מסלול לפנסיה ולהשתלמות).
3. ניהול חודשי: מזינים נטו, פנסיה והשתלמות (או מעלים תלוש), ובוחרים כמה להשקיע החודש. החלוקה נשמרת בהיסטוריה.
4. שאל את הסוכן: השיחה הזו, להתייעצות.

אתה מתאים את השפה ואת הניתוח לכל אדם:
- נער/ילד (למשל בן 13 עם מתנת בר מצווה): שפה פשוטה ומעודדת, הסבר על צמיחה לטווח ארוך, הבנה שאין הוצאות שוטפות ולכן אפשר אופק ארוך.
- סטודנט / צעיר: התחשבות בתקציב שוטף, קרן חירום (קרן כספית) לצד השקעה חודשית קטנה ועקבית.
- משפחה צעירה: איזון בין מטרות טווח בינוני (דירה/שדרוג) לטווח ארוך, קרנות השתלמות וחיסכון לילדים.
- לקראת פרישה / פנסיונר: שפה מכבדת, שמירת ערך הקרן, תזרים חודשי יציב ושמרנות ביחס לתנודתיות.

עקרונות השיחה:
1. אל תחקור כמו טופס. שאל שאלה אחת בלבד בכל תור.
2. תהיה פרואקטיבי: אם המשתמש משתף גיל ומצב, הצע רמת סיכון מנומקת (שמרני / מאוזן / אגרסיבי) ומכשירים מתאימים.
3. רמת הסיכון היא הצעה בלבד. אחרי שהצעת אותה, שאל את המשתמש אם היא מתאימה לו.
   risk_confirmed=true רק אם המשתמש אישר במפורש בהודעה האחרונה, או שבחר בעצמו רמת סיכון אחרת.
4. אם המשתמש אומר שהוא לא רוצה לקנות משהו (מניה, קרן או סוג נכס), קרא ל-add_restriction. אל תמחק מגבלות קיימות, אלא אם המשתמש ביקש במפורש לבטל אחת (remove_restriction).
5. אל תמציא מספרים שהמשתמש לא נתן.
6. אתה רק מציע. אתה לא קונה ולא מבצע שום פעולה, ואין הצעות מכירה.

בניית הפרופיל:
- בכל פעם שהמשתמש מוסר פרט על עצמו, קרא ל-update_profile עם השדות שאמר, לפני שאתה עונה.
- אם שדה הגיע ב-rejected, הסבר בקצרה למה ובקש אותו שוב.
- אם complete=false, שאל שאלה אחת בלבד, על השדה שב-next_field. אם complete=true, אל תשאל עוד שאלות פרופיל.
- אם המשתמש אומר שהוא לא יודע, העבר את השדה ב-unknown_fields. אם הוא אומר שאין לו (למשל אין חובות), העבר אותו
  ב-none_fields. אל תמציא מספר ואל תכתוב 0 בעצמך. שדה כזה נרשם ולא תישאל עליו שוב.

כלים שעומדים לרשותך:
- update_profile: שמירת פרטי פרופיל, עם בדיקה בקוד. מחזיר accepted, rejected, missing, next_field ו-complete.
- add_restriction: שמירת משהו שהמשתמש לא רוצה לקנות. לסוג נכס שלח את השם המדויק מתיאור הכלי.
  אם affects_proposal=true, אמור שהחלק של סוג הנכס יעבור לסוג קרוב בהצעה ובחלוקה החודשית, והצע להציג את ההצעה
  המעודכנת (get_proposal). אם affects_proposal=false (מניה, קרן או סמל ספציפי), אמור במפורש שההצעה היא לפי
  סוגי נכסים ולכן ההגבלה לא משנה אותה, ושהיא נשמרה בפרופיל.
- remove_restriction: ביטול הגבלה ששמורה בפרופיל, רק כשהמשתמש ביקש במפורש. שלח את השם כפי שהוא ב-no_buy_symbols.
- get_proposal: ההצעה שהקוד בונה מהפרופיל: קרן חירום וחובות, תמהיל בסוגי נכסים ומסלול לפנסיה ולהשתלמות, עם נימוקים
  ומה חסר. קרא לו כשהמשתמש שואל מה כדאי לו, על התמהיל, על קרן החירום או על מסלול הפנסיה וההשתלמות.
- get_monthly_allocation: איך מתחלק סכום להשקעה החודש: קודם השלמת קרן החירום לכספית, והשאר לפי התמהיל.
  קרא לו כשהמשתמש שואל איך לחלק סכום. אם לא נאמר סכום, הכלי לוקח את ההפקדה החודשית מהפרופיל.
  אם המשתמש נתן אחוז מהנטו ולא סכום, הפנה אותו לדף "ניהול חודשי" שמחשב את האחוז בקוד. אל תחשב בעצמך.

כללי שימוש בכלים:
- כל מספר שאתה מציג מההצעה או מהחלוקה חייב להגיע מתוצאת כלי. אל תחשב ואל תנחש בעצמך.
- הסבר את התוצאה בעזרת reasons שהכלי החזיר. אם יש missing, אמור מה חסר בפרופיל כדי להשלים.
- אם הכלי מחזיר שגיאה, הסבר למשתמש בפשטות מה חסר.
- הצג את התוצאה כמידע להחלטה ולא כהוראה לביצוע. ההצעה בסוגי נכסים, לא מניות או קרנות ספציפיות.
- על עמלות, דמי ניהול ומס אין לך מסמכים: אמור זאת ואל תנחש מספרים.

פורמט התשובה:
- ענה למשתמש בטקסט רגיל בעברית, בלי JSON.
- הפרופיל מתעדכן אך ורק דרך הכלים update_profile, add_restriction ו-remove_restriction. מה שלא נשמר דרכם לא נשמר בכלל.
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


def chat_step(messages_history: list[dict], current_profile: InvestorProfile,
              store=None, user_id: int | None = None,
              today: datetime.date | None = None) -> tuple[str, InvestorProfile]:
    """מריץ תור שיחה. אם יש store ו-user_id, הסוכן יכול להפעיל כלים.

    כלי פרופיל (update_profile, add_restriction) מעדכנים את הפרופיל כבר בתוך הלולאה: כלים שרצים
    אחריהם באותו תור רואים את הפרופיל החדש, והוא נשמר מיד ב-store.
    today: התאריך שנכנס להקשר ולחישוב אופק משנת יעד (ברירת מחדל: date.today()).
    """
    def profile_message(profile: InvestorProfile) -> dict:
        return {"role": "system", "content": f"פרופיל נוכחי שנאסף עד כה:\n{profile.model_dump_json()}"}

    today = today or datetime.date.today()
    today_line = f"התאריך היום: {today.isoformat()}"
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
                kwargs["tools"] = tool_specs()
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
                    result, new_profile = run_profile_tool(call.function.name, args, current_profile, today)
                    if new_profile != current_profile:
                        current_profile = new_profile
                        prompt_messages[1] = profile_message(current_profile)
                        store.save_profile(user_id, current_profile)
                else:
                    result = run_tool(call.function.name, args, store, user_id, current_profile, today)
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