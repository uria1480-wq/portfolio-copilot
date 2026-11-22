# Portfolio Copilot: מלאי קבצים (עודכן אחרי הריפקטור, 2026-11-22)

מספרי השורות לפי `wc -l`. "מי מייבא" כולל את הבדיקות.
הבדיקות: 475 עוברות (233 פונקציות בדיקה, חלקן עם פרמטרים), בהרצה `uv run python -m pytest -q tests`.
אין עדיין סטי הערכה (אין תיקיית evals).

**מה השתנה בריפקטור (שלב ב׳):** `proposal.py` פוצל לשלושה מודולים (`proposal`, `restrictions`, `monthly`).
נמחקו `merge_profile`, `LIST_FIELDS`, `PROTECTED_FIELDS`, `app._choice` ו-`tests/test_profile_merge.py`.
`test_gemini.py` עבר ל-`scripts/gemini_smoke_check.py`. אוחדו פונקציות כפולות (ראו סעיף 5).
`share=True` כבר לא קבוע בקוד: הוא עובר לדגל `--share` עם סיסמה מ-`.env`. אזהרות התלוש מוצגות.
להיסטוריית השיחה ולתשובת המודל יש תקרה.

## 1. קוד: `src/portfolio_copilot/`

| קובץ | שורות | מה הוא עושה | מי מייבא אותו | מה הוא מייבא | LLM? | פסק |
| --- | --- | --- | --- | --- | --- | --- |
| `__init__.py` | 0 | קובץ ריק שהופך את התיקייה לחבילה | כל `from portfolio_copilot...` | — | לא | להשאיר. נקודת הכניסה ב-`pyproject.toml` תוקנה ל-`portfolio_copilot.app:main` |
| `agent.py` | 200 | פרומפט המערכת, `chat_step` (לולאת כלים חסומה), תקרות (`MAX_TOOL_ROUNDS=4`, `MAX_HISTORY_MESSAGES=20`, `MAX_REPLY_TOKENS=2048`), `recent_history`, `read_payslip`. מחזיק את ה-client ואת שם המודל | `app.py`, `scripts/latency_check.py`, בדיקות: agent_flow, flow, parsing, profile_tools, wiring | `openai`, `dotenv`, `schemas`, `documents` (`extract_json`, `read_document`), `agent_tools` | **כן** | להשאיר |
| `agent_tools.py` | 240 | הגדרות 5 הכלים שהמודל רואה, והרצתם | `agent.py`, בדיקות: agent_tools, profile_tools, restrictions, wiring | `db` (`ALL_HISTORY`), `monthly`, `proposal`, `restrictions`, `schemas` | לא | להשאיר |
| `app.py` | 371 | ממשק Gradio: 4 לשונות, חיווט, `--fresh`, `--share` (`share_settings`), handler אחד לתלוש (`make_payslip_handler`, עם הודעה לשלך או לבן/בת הזוג) | נקודת הכניסה; בדיקה: flow | `gradio`, `agent`, `db`, `monthly`, `proposal`, `schemas`, `situation`, `ui` | לא (קורא ל-`chat_step` ו-`read_payslip` בלבד) | להשאיר. `build_demo` עדיין ארוכה (פריסה וחיווט יחד), וזה מקובל ב-Gradio |
| `db.py` | 146 | SQLite: משתמשים, פרופיל כ-JSON, תלושים, דיווחים חודשיים | `app.py`, `agent_tools.py`, רוב הבדיקות | `sqlite3`, `schemas` | לא | להשאיר. 4 טבלאות מגרסאות קודמות נשארות בכוונה, עם הערה בקוד. `documents` נכתבת ולא נקראת |
| `documents.py` | 206 | קריאת תלוש: PDF לטקסט, תיקון עברית, הסתרת מזהים, חילוץ ב-LLM ל-`Payslip`, בדיקות חשבון. גם `extract_json`, המשותף לסוכן ולתלוש | `agent.py`, בדיקות: documents, parsing | `pydantic`, `pdfplumber` ו-`bidi` (שניהם נטענים רק כשצריך) | **כן** (`extract_payslip`, עם client מ-`agent`) | להשאיר |
| `proposal.py` | 283 | "קבל הצעה": קרן חירום, חוב, תמהיל (`equity_percent`, `allocation_percents`, `_mix`), `_split`, מסלול פנסיה, `build_proposal` | `app.py`, `agent_tools.py`, `monthly.py`, `ui.py`, בדיקות: proposal, restrictions, agent_tools | `pydantic`, `restrictions`, `schemas` | לא | להשאיר |
| `restrictions.py` | 142 | **חדש.** שמות 5 סוגי הנכסים, `SUBSTITUTES`, ניסוחים נפוצים, קבוצות ("מניות", "אג"ח"), `restriction_target`, `apply_restrictions`, `emergency_asset_class` | `proposal.py`, `monthly.py`, `agent_tools.py`, בדיקות: restrictions, proposal | `schemas` בלבד | לא | להשאיר |
| `monthly.py` | 211 | **חדש.** `allocate_monthly`, `emergency_deposited`, `default_savings_percent`, `monthly_report`, `MonthlyReport`, `history_row` | `app.py`, `agent_tools.py`, `ui.py`, בדיקות: proposal, restrictions, agent_tools | `pydantic`, `proposal` (עזרים `_needs`, `_emergency`, `_mix`, `_split` ועוד), `restrictions`, `schemas` | לא | להשאיר |
| `schemas.py` | 316 | `InvestorProfile`, `is_partnered()`, `missing_fields()`, ולידציה לכל שדה (`apply_profile_update`), שנת יעד לאופק, `format_money` | כל המודולים, רוב הבדיקות | `pydantic` | לא | להשאיר |
| `situation.py` | 114 | תמונת המצב ל"המצב שלי": ערך ומקור לכל שדה, תוספות מהדיווחים, מה חסר | `app.py`, בדיקה: situation | `schemas` | לא | להשאיר |
| `ui.py` | 416 | CSS ופונקציות HTML: פרופיל, התקדמות, שלבים, תמונת מצב, הצעה, דיווח חודשי, היסטוריה, `payslip_status_html` (הודעה ואזהרות תלוש) | `app.py`, בדיקות: ui, flow, proposal, situation | `html`, `inspect`, `monthly`, `proposal`, `schemas` | לא | להשאיר. אפשר להוציא את ה-CSS לקובץ נפרד, לא דחוף |

**כיוון התלויות בין שלושת מודולי החישוב:** `restrictions` ← `proposal` ← `monthly`, בלי יבוא מעגלי (נבדק ב-`test_split_modules_depend_one_way`).

## 2. בדיקות: `tests/`

כל הבדיקות מחליפות את ה-client ב-LLM מדומה, ואף אחת לא פונה לרשת.

| קובץ | שורות | מה הוא בודק | מה הוא מייבא | LLM? | פסק |
| --- | --- | --- | --- | --- | --- |
| `test_agent_flow.py` | 139 | לולאת הכלים, התאריך בהקשר, עצירת לולאה אינסופית, רק 20 ההודעות האחרונות נשלחות, `max_tokens` בכל קריאה, שם הקורס בפרומפט | `agent`, `db`, `schemas` | מדומה | להשאיר |
| `test_agent_tools.py` | 62 | `get_proposal` ו-`get_monthly_allocation` מחזירים את מה שהקוד חישב | `agent_tools`, `db`, `monthly`, `proposal`, `schemas` | לא | להשאיר |
| `test_db.py` | 61 | משתמשים, פרופיל הלוך-חזור, דיווחים, ניקוי "לא למכור" בטעינה | `db`, `schemas` | לא | להשאיר |
| `test_documents.py` | 111 | עברית הפוכה, הסתרת מזהים, ניקוי מספרים, בדיקות חשבון, נשלח רק טקסט מוסתר | `documents`, `db`, `schemas` | מדומה | להשאיר |
| `test_flow.py` | 565 | זרימות דרך ה-handlers: ראיון, `--fresh`, `--share` וסיסמה, נקודת הכניסה, דיווח חודשי, תלוש ואזהרות, זוגות, קרן חירום, דשבורד | `agent`, `app`, `db`, `schemas`, `ui` | מדומה | להשאיר. הוא הקובץ הגדול ביותר, ואפשר לפצל אותו בהמשך (ראו שאלות פתוחות) |
| `test_parsing.py` | 94 | `final_reply_text`, ו-`extract_json` המשותף לסוכן ולתלוש | `agent`, `documents`, `schemas` | מדומה | להשאיר |
| `test_profile_tools.py` | 430 | `update_profile` ו-`add_restriction`, "לא יודע"/"אין", זוגות (`is_partnered`), `is_complete` (הבדיקה הועברה לכאן מ-`test_profile_merge.py`) | `agent`, `agent_tools`, `db`, `schemas` | מדומה | להשאיר |
| `test_proposal.py` | 490 | חוקי ההצעה, החלוקה החודשית, ברירת מחדל לאחוז. מוודא ששלושת מודולי החישוב לא מייבאים openai ותלויים זה בזה בכיוון אחד | `proposal`, `monthly`, `restrictions`, `schemas`, `db`, `ui` | לא | להשאיר |
| `test_restrictions.py` | 239 | "אל תקנה": תחליפים, קבוצות, ניסוחים, הסרה | `agent_tools`, `db`, `monthly`, `proposal`, `restrictions`, `schemas` | לא | להשאיר |
| `test_situation.py` | 163 | תמונת המצב: מקורות, "—", תוספות מדיווחים | `db`, `schemas`, `situation`, `ui` | לא | להשאיר |
| `test_ui.py` | 46 | HTML: מצבי פרופיל, escaping, באנר, `supported`, hero, ושעיצוב כסף נמצא במקום אחד | `schemas`, `ui`, `proposal`, `restrictions`, `monthly`, `situation` | לא | להשאיר |
| `test_wiring.py` | 40 | הסוכן רואה בדיוק 5 כלים, והפרומפט לא מזכיר כלים שהוסרו | `agent`, `agent_tools`, `db`, `schemas` | מדומה | להשאיר |

## 3. שורש הפרויקט ו-`scripts/`

| קובץ | שורות | מה הוא עושה | מי מייבא אותו | מה הוא מייבא | LLM? | פסק |
| --- | --- | --- | --- | --- | --- | --- |
| `pyproject.toml` | 30 | תלויות ונקודת כניסה | uv | — | — | להשאיר. `portfolio-copilot = "portfolio_copilot.app:main"`. ליד `pandas<3` יש הערה: לא מיובא בקוד, ו-gradio תלוי בו |
| `README.md` | 48 | התקנה, הרצה (כולל `--share` ו-`SHARE_PASSWORD`), בדיקות, מבנה | — | — | — | להשאיר |
| `CLAUDE.md` | 25 | כללי העבודה לסוכן הקוד | — | — | — | להשאיר |
| `scripts/gemini_smoke_check.py` | 25 | **הועבר מ-`test_gemini.py`.** בדיקה ידנית של חיבור ל-Gemini | אף אחד | `openai`, `dotenv` | **כן, אמיתי** | להשאיר. השם לא מתחיל ב-`test_`, ולכן pytest לא אוסף אותו (יש על זה בדיקה) |
| `scripts/latency_check.py` | 152 | מדידת זמני תגובה של המודל | אף אחד (מורץ ידנית) | `agent` | **כן, אמיתי** | להשאיר |

## 4. קוד שלא בשימוש (מה שנשאר)

| שם | איפה | הערה |
| --- | --- | --- |
| טבלאות `holdings`, `deposits`, `plans`, `state` | `db.py` SCHEMA | נשארות בכוונה, כדי לא לשנות מסד קיים |
| טבלת `documents` | `db.py` | נכתבת ב-`save_document`, ואין קוד שקורא ממנה |
| `Store.close` | `db.py` | רק בבדיקות |
| שדות `initial_amount`, `needs_cashflow`, `life_stage`, `relevant_vehicles`, `agent_reasoning` | `schemas.py` | נאספים ומוצגים בכרטיס הפרופיל, ואף חוק לא משתמש בהם |

## 5. קוד כפול: מה אוחד ומה נשאר

| מה | מצב |
| --- | --- |
| עיצוב סכום `₪x` | **אוחד** ל-`schemas.format_money`. `proposal`, `ui` ו-`situation.format_value` קוראים לה |
| חילוץ JSON מטקסט | **אוחד** ל-`documents.extract_json` (עם `strict=False`). `agent` מייבא אותה |
| "האם בזוגיות" | **אוחד** למתודה `InvestorProfile.is_partnered()`. נמחקו `spouse_income_required` ו-`proposal.partner_fields_shown`, וגם חוק קרן החירום משתמש בה |
| handler לתלוש | **אוחד** ל-`make_payslip_handler(store, user_id, success_message)` עם `PAYSLIP_OK` / `PARTNER_PAYSLIP_OK` |
| "האם הפרופיל מלא" בשתי הגדרות | נשאר: `is_complete` (מוכן לחישוב) לעומת `missing_fields()` (הראיון גמור). יש לזה סיבה, אבל צריך לדעת להסביר |
| קריאת רשומות ישנות | נשאר ב-`situation._sum` וב-`monthly.history_row` |
| `bonds_share` | נשאר: מחושב ב-`allocation_percents` וגם ב-`_mix` |
| תיאור הכלים | נשאר: גם ב-`agent_tools` וגם ב-`SYSTEM_PROMPT` |

## 6. קבצים גדולים

| קובץ | שורות | הערה |
| --- | --- | --- |
| `tests/test_flow.py` | 565 | הקובץ הכי גדול. אפשר לפצל לראיון, חודשי והפעלה |
| `ui.py` | 416 | כולל כ-90 שורות CSS |
| `app.py` | 371 | `build_demo` ארוכה |
| `schemas.py` | 316 | ירד מ-354 אחרי מחיקת `merge_profile` |

## 7. ממצאי הסקירה: מה טופל

| ממצא | מצב |
| --- | --- |
| אזהרות התלוש לא מוצגות | **טופל:** `ui.payslip_status_html` מציג אותן מתחת להודעת הקריאה |
| `test_gemini.py` נאסף על ידי pytest | **טופל:** הועבר ל-`scripts/gemini_smoke_check.py` |
| נקודת הכניסה שבורה | **טופל:** `portfolio_copilot.app:main` |
| הלולאה חסומה רק בסבבים | **טופל:** נוספו `MAX_HISTORY_MESSAGES=20` ו-`MAX_REPLY_TOKENS=2048` |
| שם הקורס בפרומפט | **טופל** |
| `share=True` וסיסמה בקוד | **טופל:** `--share` וסיסמה מ-`SHARE_PASSWORD` |
| סט הערכה | **פתוח** |
