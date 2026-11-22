# Portfolio Copilot: מלאי קבצים (סקירה, 2026-11-22)

סקירה בלבד. שום קוד לא שונה. מספרי השורות לפי `wc -l`. "מי מייבא" כולל את הבדיקות.
מצב הבדיקות בזמן הסקירה: 458 עוברות (221 פונקציות בדיקה, חלקן עם פרמטרים).
אין בפרויקט סטי הערכה (אין תיקיית evals), ולכן לא היה מה לחכות לו.

## 1. קוד: `src/portfolio_copilot/`

| קובץ | שורות | מה הוא עושה | מי מייבא אותו | מה הוא מייבא | LLM? | פסק |
| --- | --- | --- | --- | --- | --- | --- |
| `__init__.py` | 0 | קובץ ריק שהופך את התיקייה לחבילה | כל `from portfolio_copilot...` | — | לא | **להשאיר**, אבל ב-`pyproject.toml` מוגדר `portfolio-copilot = "portfolio_copilot:main"` ואין `main` בקובץ הזה. הפקודה `portfolio-copilot` שבורה: צריך לתקן את ה-script או למחוק אותו |
| `agent.py` | 200 | פרומפט המערכת, `chat_step` (לולאת כלים חסומה ב-`MAX_TOOL_ROUNDS=4`), `read_payslip`. מחזיק את ה-client ואת שם המודל | `app.py`, `scripts/latency_check.py`, בדיקות: agent_flow, flow, parsing, profile_tools, wiring | `openai`, `dotenv`, `schemas`, `documents`, `agent_tools` | **כן** | **להשאיר**. `extract_json`, `salvage_reply` ו-`final_reply_text` הם שארית מהתקופה שבה המודל החזיר JSON. היום המודל מתבקש לענות בטקסט, ולכן אפשר לצמצם אותן, אבל הן הגנה זולה |
| `agent_tools.py` | 239 | הגדרות 5 הכלים שהמודל רואה (`update_profile`, `add_restriction`, `remove_restriction`, `get_proposal`, `get_monthly_allocation`) והרצתם | `agent.py`, בדיקות: agent_tools, profile_tools, restrictions, wiring | `db` (רק `ALL_HISTORY`), `proposal`, `schemas` | לא | **להשאיר** |
| `app.py` | 359 | ממשק Gradio: 4 לשונות, חיווט כפתורים ל-handlers, `--fresh`, הפעלה | נקודת הכניסה; בדיקה: flow | `gradio`, `agent`, `db`, `proposal`, `schemas`, `situation`, `ui` | לא (קורא ל-`chat_step` ו-`read_payslip` בלבד) | **להשאיר**. `_choice` (שורה 192) לא בשימוש. `make_payslip_handler` ו-`make_partner_payslip_handler` כמעט זהים. שם משתמש וסיסמה ל-`share=True` כתובים בקוד |
| `db.py` | 146 | SQLite: משתמשים, פרופיל כ-JSON, תלושים, דיווחים חודשיים | `app.py`, `agent_tools.py`, בדיקות: כמעט כולן | `sqlite3`, `schemas` | לא | **להשאיר**. 4 טבלאות לא בשימוש (holdings, deposits, plans, state). טבלת `documents` נכתבת (`save_document`) ואף אחד לא קורא ממנה. `close` נקרא רק בבדיקות |
| `documents.py` | 203 | קריאת תלוש: PDF לטקסט, תיקון עברית הפוכה, הסתרת מזהים, חילוץ ב-LLM לסכמת `Payslip`, בדיקות חשבון | `agent.py`, בדיקה: documents | `pydantic`, `pdfplumber` (מאוחר), `bidi` (מאוחר) | **כן** (`extract_payslip`, עם client שמגיע מ-`agent`) | **להשאיר**. **ממצא:** האזהרות של `check_payslip` (`warnings`) לא מוצגות למשתמש בשום מקום: `app._read_payslip` לוקח רק את `summary`. `_parse_json` כפול עם `agent.extract_json` |
| `proposal.py` | 622 | כל החוקים: קרן חירום, חוב, תמהיל, הגבלות "אל תקנה", מסלול פנסיה, חלוקה חודשית, דיווח חודשי, ברירת מחדל לאחוז, שורת היסטוריה | `app.py`, `agent_tools.py`, `ui.py`, בדיקות: proposal, restrictions, agent_tools, flow | `pydantic`, `schemas` | לא | **להשאיר, אבל גדול מדי.** עושה ארבעה דברים. אפשר לפצל: הגבלות (`ASSET_CLASS_ALIASES` עד `emergency_asset_class`, כ-115 שורות) ל-`restrictions.py`, ודיווח חודשי (`MonthlyAllocation` עד `history_row`, כ-200 שורות) ל-`monthly.py` |
| `schemas.py` | 354 | `InvestorProfile` (Pydantic), סדר שאלות הראיון, ולידציה לכל שדה (`apply_profile_update`), "לא יודע"/"אין", שנת יעד לאופק | כל המודולים, רוב הבדיקות | `pydantic` | לא | **להשאיר**. `merge_profile` (כ-40 שורות) עם `LIST_FIELDS` ו-`PROTECTED_FIELDS` הם קוד מת: רק הבדיקות קוראות להם. הכלי `update_profile` עובר דרך `apply_profile_update` |
| `situation.py` | 114 | תמונת המצב ל"המצב שלי": ערך ומקור לכל שדה, תוספות מהדיווחים, מה חסר | `app.py`, בדיקה: situation | `schemas` | לא | **להשאיר**. `load_situation` היא עטיפה של שורה אחת |
| `ui.py` | 405 | CSS (כ-90 שורות) ופונקציות שמחזירות HTML: פרופיל, התקדמות, שלבים, תמונת מצב, הצעה, דיווח חודשי, היסטוריה | `app.py`, בדיקות: ui, flow, proposal, situation | `html`, `inspect`, `proposal` (`MonthlyReport`, `Proposal`, `history_row`), `schemas` | לא | **להשאיר**. `_money` כפול עם `proposal._money` |

## 2. בדיקות: `tests/`

כל הבדיקות מחליפות את ה-client ב-LLM מדומה (`monkeypatch` על `agent.client`), ולכן אף אחת לא פונה לרשת.

| קובץ | שורות | מה הוא בודק | מה הוא מייבא | LLM? | פסק |
| --- | --- | --- | --- | --- | --- |
| `test_agent_flow.py` | 108 | לולאת הכלים: סבב כלי ותשובה, בלי store אין כלים, התאריך בהקשר, לולאה אינסופית נעצרת | `agent`, `db`, `schemas` | מדומה | להשאיר |
| `test_agent_tools.py` | 61 | `get_proposal` ו-`get_monthly_allocation`: מחזירים את מה שהקוד חישב, שגיאות חוזרות כ-error | `agent_tools`, `db`, `proposal`, `schemas` | לא | להשאיר |
| `test_db.py` | 61 | משתמשים, פרופיל הלוך-חזור, דיווחים, ניקוי "לא למכור" בטעינה | `db`, `schemas` (כולל `merge_profile`) | לא | להשאיר. הבדיקה הראשונה משתמשת ב-`merge_profile`, ותצטרך שינוי אם הוא יימחק |
| `test_documents.py` | 111 | עברית הפוכה, הסתרת מזהים, ניקוי מספרים, בדיקות חשבון, נשלח רק טקסט מוסתר | `documents`, `db`, `schemas` | מדומה | להשאיר |
| `test_flow.py` | 477 | זרימות מקצה לקצה דרך ה-handlers של `app.py`: ראיון, `--fresh`, דיווח חודשי, תלוש, זוגות, קרן חירום, דשבורד, גבול ה-client | `agent`, `app`, `db`, `schemas`, `ui` | מדומה | להשאיר. גדול מדי (34 בדיקות על נושאים שונים). אפשר לפצל ל-`test_monthly_flow.py` ול-`test_intake_flow.py` |
| `test_parsing.py` | 76 | `final_reply_text`: טקסט רגיל, JSON עם reply, JSON שבור, תשובה ריקה | `agent`, `schemas` | מדומה | להשאיר כל עוד `final_reply_text` קיים |
| `test_profile_merge.py` | 37 | `merge_profile`: רשימות מתמזגות, null לא דורס, שינוי סיכון מאפס אישור | `schemas` | לא | **למחוק יחד עם `merge_profile`**. הבדיקה `test_complete_requires_user_confirmation` בודקת את `is_complete` ושווה להעביר אותה ל-`test_profile_tools.py` |
| `test_profile_tools.py` | 422 | `update_profile` ו-`add_restriction`: ולידציה, שנת יעד, "לא יודע"/"אין", זוגות, ראיון מרובה תורות | `agent`, `agent_tools`, `db`, `schemas` | מדומה | להשאיר |
| `test_proposal.py` | 479 | כל חוקי ההצעה והחלוקה החודשית, ברירת מחדל לאחוז, ש-`proposal.py` לא מייבא openai | `proposal`, `schemas`, `db`, `ui` | לא | להשאיר |
| `test_restrictions.py` | 238 | "אל תקנה": תחליפים, קבוצות, ניסוחים, הסרה, ניקוי פרופיל ישן | `agent_tools`, `db`, `proposal`, `schemas` | לא | להשאיר |
| `test_situation.py` | 163 | תמונת המצב: מקורות, "—", תוספות מדיווחים, רשומות ישנות | `db`, `schemas`, `situation`, `ui` | לא | להשאיר |
| `test_ui.py` | 34 | HTML: מצבי פרופיל, escaping, באנר, `supported`, טקסט ה-hero | `schemas`, `ui` | לא | להשאיר |
| `test_wiring.py` | 40 | הסוכן רואה בדיוק 5 כלים, ופרומפט המערכת לא מזכיר כלים שהוסרו | `agent`, `agent_tools`, `db`, `schemas` | מדומה | להשאיר |

## 3. שורש הפרויקט

| קובץ | שורות | מה הוא עושה | מי מייבא אותו | מה הוא מייבא | LLM? | פסק |
| --- | --- | --- | --- | --- | --- | --- |
| `test_gemini.py` | 25 | בדיקה ידנית ראשונה של חיבור ל-Gemini: שולח שאלה אחת ומדפיס | אף אחד, **אבל pytest אוסף אותו** | `openai`, `dotenv` | **כן, אמיתי** | **למחוק** (או להעביר ל-`scripts/` בשם אחר). השם מתחיל ב-`test_` והוא בשורש, ולכן `pytest` מייבא אותו ושולח בקשה אמיתית ל-API בכל הרצה (יש `__pycache__/test_gemini.cpython-312-pytest-9.2.0.pyc`, כלומר pytest כבר ייבא אותו). לא הרצתי אותו כדי לא לשלוח בקשה |
| `pyproject.toml` | 30 | תלויות ונקודת כניסה | uv | — | — | להשאיר ולתקן: `pandas<3` לא מיובא בקוד (אולי הגבלת גרסה מכוונת בשביל gradio), `description` עדיין "Add your description here", ו-`[project.scripts]` שבור (ראו `__init__.py`) |
| `README.md` | 47 | התקנה, הרצה, בדיקות, מבנה | — | — | — | להשאיר |
| `CLAUDE.md` | 25 | כללי העבודה לסוכן הקוד | — | — | — | להשאיר |
| `scripts/latency_check.py` | 152 | מדידת זמני תגובה של המודל מחוץ לאפליקציה | אף אחד (מורץ ידנית) | `agent` (`MODEL_NAME`, `SYSTEM_PROMPT`, `client`) | **כן, אמיתי** | להשאיר. כלי מדידה, לא חלק מהאפליקציה |

`design/` (big_vision, mvp, modules) לא נכלל בטבלה. הערה אחת: `big_vision.md` עדיין מזכיר SciPy, yfinance, RAG ותיקון עצמי, שלא נמצאים בקוד. זה בסדר כי זה החזון, אבל בבחינה צריך לדעת להסביר את הפער (ראו study_guide, החלטות 3 ו-9).

## 4. פונקציות וקבועים שאף אחד לא קורא להם (בקוד, לא בבדיקות)

| שם | איפה | הערה |
| --- | --- | --- |
| `merge_profile` | `schemas.py:318` | רק `test_profile_merge.py` ו-`test_db.py` קוראים לו. הכלי `update_profile` משתמש ב-`apply_profile_update` |
| `LIST_FIELDS`, `PROTECTED_FIELDS` | `schemas.py:108-110` | בשימוש רק בתוך `merge_profile` |
| `_choice` | `app.py:192` | לא נקרא בשום מקום (ב-`schemas.py` יש `_choice` אחר, שכן בשימוש) |
| `Store.close` | `db.py` | רק בבדיקות. האפליקציה לא סוגרת את החיבור (זה תקין לתהליך שרץ עד היציאה) |
| טבלאות `holdings`, `deposits`, `plans`, `state` | `db.py` SCHEMA | נשארו בכוונה כדי לא לשנות מסד קיים (כתוב בהערה) |
| טבלת `documents` | `db.py` | נכתבת ב-`save_document`, אבל אין קוד שקורא ממנה |
| השדה `warnings` של התלוש | `documents.read_document` | מחושב, נשמר במסד, ולא מוצג. `app._read_payslip` לוקח רק את `summary` |
| שדות פרופיל `initial_amount`, `needs_cashflow`, `life_stage`, `relevant_vehicles`, `agent_reasoning` | `schemas.py` | נאספים ומוצגים בכרטיס הפרופיל, אבל אף חוק ב-`proposal.py` לא משתמש בהם (`life_stage` רק מחליף גיל ב-`missing_fields`) |

## 5. קוד כפול

| מה | איפה | הצעה |
| --- | --- | --- |
| עיצוב סכום `f"₪{x:,.0f}"` | `proposal._money`, `ui._money`, `situation.format_value("money")` | פונקציה אחת (למשל ב-`schemas.py` או במודול קטן `format.py`) |
| חילוץ JSON מטקסט (אותו regex `\{.*\}`) | `agent.extract_json`, `documents._parse_json` | `documents` יכול להשתמש בפונקציה אחת. ההבדל היחיד הוא `strict=False` |
| "האם בזוגיות" (`marital_status in PARTNERED_STATUSES`) | `InvestorProfile.spouse_income_required`, `proposal.partner_fields_shown` | אותה בדיקה בשני שמות. אפשר ש-`partner_fields_shown` תקרא למתודה |
| "האם הפרופיל מלא" בשתי הגדרות | `InvestorProfile.is_complete` (גיל, סיכון מאושר, אופק) ו-`not missing_fields()` (כל שדות הראיון) | `ui.profile_html` משתמש בראשונה ו-`app.stage_flags` בשנייה. לכן ייתכן שכרטיס הפרופיל יראה "מוכן לחישוב" כשהשלב עוד לא סומן כבוצע |
| handler לתלוש | `app.make_payslip_handler`, `app.make_partner_payslip_handler` | נבדלים רק בהודעת ההצלחה. פונקציה אחת עם פרמטר |
| קריאת רשומות ישנות עם שדה חלופי | `situation._sum(key, fallback)`, `proposal.history_row` | שני מקומות שיודעים על אותה תאימות לאחור. סביר להשאיר |
| `bonds_share` לפי האופק | `proposal.allocation_percents`, `proposal._mix` | מחושב פעמיים. פונקציה קטנה אחת |
| תיאור הכלים | `agent_tools` (description של כל כלי) ו-`SYSTEM_PROMPT` (סעיף "כלים שעומדים לרשותך") | שני מקורות לאותו הסבר. אם אחד משתנה, צריך לזכור לעדכן גם את השני |

## 6. קבצים גדולים או כאלה שעושים כמה דברים

| קובץ | שורות | למה |
| --- | --- | --- |
| `proposal.py` | 622 | ארבעה תחומים: (1) הצעה, (2) הגבלות "אל תקנה" וזיהוי סוג נכס, (3) חלוקה ודיווח חודשי עם היסטוריה, (4) ברירת מחדל לאחוז. הקוד טהור ונבדק היטב, ולכן פיצול הוא שינוי בטוח יחסית |
| `ui.py` | 405 | כ-90 שורות CSS ועוד HTML לכל מסך. אפשר להוציא את ה-CSS לקובץ `.css`, אבל זה לא דחוף |
| `app.py` | 359 | `build_demo` לבדה כ-130 שורות (פריסה וחיווט יחד). זה מקובל ב-Gradio |
| `schemas.py` | 354 | מודל, ולידציה, לוגיקת "לא יודע"/"אין" ו-`merge_profile` המת. בלי `merge_profile` יורד לכ-310 |
| `tests/test_flow.py` | 477 | מכסה את כל המסכים בקובץ אחד |

## 7. ממצאים נוספים (לא איחוד או מחיקה)

1. **אזהרות התלוש לא מוצגות.** `documents.py` אומר בתיעוד שלו "התוצאה מסומנת כדי שהסוכן יבקש מהמשתמש לאמת", אבל אף אחד לא מציג את `warnings`. בבחינה זו תהיה שאלה טבעית.
2. **`test_gemini.py` נאסף על ידי pytest** ושולח בקשה אמיתית בכל `uv run python -m pytest -q`.
3. **נקודת הכניסה `portfolio-copilot` שבורה** (`portfolio_copilot:main` לא קיים).
4. **הלולאה חסומה במספר סבבים, לא בעלות.** `CLAUDE.md` מדבר על "מספר סבבים ועלות". יש `MAX_TOOL_ROUNDS=4`, `timeout=30` ו-`max_retries=2`, אבל אין תקרת טוקנים.
5. **סט הערכה לא קיים**, למרות שהוא בתחום ה-MVP (`mvp.md`).
6. **`SYSTEM_PROMPT` אומר "בקורס מבוא לבינה מלאכותית"**, ושם הקורס ב-`CLAUDE.md` הוא "פיתוח פתרונות מבוססי AI".
7. **`share=True` עם סיסמה קבועה בקוד** (`app.py:355`): כל הרצה פותחת קישור ציבורי.

## 8. סיכום הפסקים (מה לאחד, לפצל או למחוק). לא בוצע

| מה | פסק | למה |
| --- | --- | --- |
| `test_gemini.py` | למחוק (או להעביר ל-`scripts/`) | pytest אוסף אותו ושולח בקשה אמיתית בכל הרצה. `scripts/latency_check.py` כבר בודק חיבור |
| `schemas.merge_profile`, `LIST_FIELDS`, `PROTECTED_FIELDS` | למחוק | קוד מת: רק בדיקות קוראות להם |
| `tests/test_profile_merge.py` | למחוק (את בדיקת `is_complete` להעביר) | בודק רק את `merge_profile` |
| `app._choice` | למחוק | לא נקרא |
| `make_payslip_handler` + `make_partner_payslip_handler` | לאחד לפונקציה אחת עם פרמטר | זהים חוץ מהודעה |
| `proposal._money`, `ui._money`, `situation.format_value("money")` | לאחד | אותו עיצוב בשלושה מקומות |
| `documents._parse_json` + `agent.extract_json` | לאחד | אותו regex |
| `partner_fields_shown` + `spouse_income_required` | לאחד | אותה בדיקה |
| `proposal.py` | לפצל ל-`restrictions.py` ו-`monthly.py` | 622 שורות, ארבעה תחומים |
| `tests/test_flow.py` | לפצל (אופציונלי) | 477 שורות, כל המסכים |
| טבלאות DB לא בשימוש | להשאיר | מחיקה משנה מסד קיים, ואין בזה תועלת |
| `[project.scripts]` ב-`pyproject.toml` | לתקן או למחוק | מצביע על `main` שלא קיים |
