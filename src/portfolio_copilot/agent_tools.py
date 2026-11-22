"""חיבור הכלים לסוכן: הגדרות הכלים שה-LLM רואה, והפונקציה שמריצה אותם.
כל מספר שהסוכן מציג מגיע מכאן (proposal.py), לא מחישוב של המודל."""
import re
from datetime import date

from portfolio_copilot.db import ALL_HISTORY
from portfolio_copilot.monthly import allocate_monthly, amount_from_percent_of_net, emergency_deposited
from portfolio_copilot.proposal import build_proposal
from portfolio_copilot.restrictions import ASSET_CLASSES, ASSET_GROUPS, classes_blocked_by, restriction_target
from portfolio_copilot.schemas import (EMPLOYMENT_OPTIONS, LIFE_STAGES, MARITAL_OPTIONS, NONE_ALLOWED, RISK_LEVELS,
                                       UNKNOWN_ALLOWED, InvestorProfile, apply_profile_update)

PROFILE_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": (
                "שומר בפרופיל ערכים שהמשתמש אמר. כל ערך נבדק בקוד: התוצאה מחזירה מה התקבל (accepted), "
                "מה נדחה ולמה (rejected), מה עוד חסר (missing) ואת השדה הבא לשאול עליו (next_field). "
                "שלח רק שדות שהמשתמש אמר במפורש. risk_confirmed=true רק אם המשתמש אישר במפורש את רמת הסיכון. "
                "אם המשתמש אמר שהוא לא יודע, שלח את שם השדה ב-unknown_fields. אם אמר שאין לו, שלח אותו ב-none_fields. "
                "אל תמציא מספר או 0 בעצמך. הכנסת בן/בת הזוג נשאלת רק אם marital_status הוא נשוי או ידוע בציבור. "
                "אם המשתמש אמר שבן/בת הזוג לא עובד/ת או בלי הכנסה, שלח spouse_monthly_net_income ב-none_fields. "
                "אם המשתמש נקב בשנת יעד (למשל 2029), שלח target_year ולא investment_horizon_years: הקוד מחשב את האופק "
                "בשנים מול התאריך של היום. אל תחשב שנים בעצמך."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "age": {"type": "integer", "description": "גיל, 0 עד 120"},
                    "life_stage": {"type": "string", "enum": list(LIFE_STAGES)},
                    "initial_amount": {"type": "number", "description": "סכום ראשוני להשקעה, לא שלילי"},
                    "monthly_deposit": {"type": "number", "description": "הפקדה חודשית שהמשתמש בחר, לא שלילית"},
                    "needs_cashflow": {"type": "boolean"},
                    "investment_goal": {"type": "string"},
                    "investment_horizon_years": {"type": "integer", "description": "אופק בשנים, 1 עד 80"},
                    "target_year": {
                        "type": "integer",
                        "description": "שנת יעד שהמשתמש אמר, למשל 2029. הקוד מחשב ממנה את investment_horizon_years (1 עד 80)",
                    },
                    "recommended_risk_level": {"type": "string", "enum": list(RISK_LEVELS)},
                    "risk_confirmed": {"type": "boolean"},
                    "relevant_vehicles": {"type": "array", "items": {"type": "string"}},
                    "agent_reasoning": {"type": "string", "description": "נימוק קצר לרמת הסיכון"},
                    "marital_status": {"type": "string", "enum": list(MARITAL_OPTIONS)},
                    "spouse_monthly_net_income": {
                        "type": "number",
                        "description": "הכנסה נטו חודשית של בן/בת הזוג בשקלים, לא שלילית. רק לנשוי או ידוע בציבור",
                    },
                    "employment_status": {"type": "string", "enum": list(EMPLOYMENT_OPTIONS)},
                    "monthly_net_income": {"type": "number", "description": "הכנסה נטו חודשית בשקלים, לא שלילית"},
                    "monthly_expenses": {"type": "number", "description": "הוצאות חודשיות בשקלים, לא שליליות"},
                    "liquid_savings": {"type": "number", "description": "כסף נזיל וחסכונות בבנק בשקלים, לא שלילי"},
                    "monthly_debt_payments": {"type": "number", "description": "החזרי הלוואות או משכנתא בחודש, לא שליליים"},
                    "pension_balance": {"type": "number", "description": "יתרה בקרן הפנסיה, לא שלילית"},
                    "study_fund_balance": {"type": "number", "description": "יתרה בקרן ההשתלמות, לא שלילית"},
                    "other_assets": {"type": "number", "description": "שווי נכסים אחרים, לא שלילי"},
                    "unknown_fields": {
                        "type": "array", "items": {"type": "string", "enum": list(UNKNOWN_ALLOWED)},
                        "description": "שדות שהמשתמש אמר שהוא לא יודע. נרשמים ולא נשאלים שוב",
                    },
                    "none_fields": {
                        "type": "array", "items": {"type": "string", "enum": list(NONE_ALLOWED)},
                        "description": "שדות שהמשתמש אמר עליהם במפורש שאין לו. רק שדות שנאמרו. הקוד רושם 0",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_restriction",
            "description": (
                "שומר בפרופיל משהו שהמשתמש אמר שהוא לא רוצה לקנות. אם זה אחד מסוגי הנכסים "
                f"({', '.join(ASSET_CLASSES)}) או קבוצה שלמה ({', '.join(ASSET_GROUPS)}), שלח את השם כך: "
                "ההצעה והחלוקה החודשית יעבירו את החלק שלו לסוג קרוב (affects_proposal=true). "
                "מניה, קרן או סמל ספציפי (למשל TSLA) נשמרים, "
                "אבל לא משנים את ההצעה כי היא בסוגי נכסים (affects_proposal=false)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "מה לא לקנות: שם מדויק של סוג נכס (למשל אג\"ח קונצרני), או סמל/שם של מניה או קרן (למשל TSLA)"},
                    "kind": {"type": "string", "enum": ["no_buy"], "description": "סוג המגבלה"},
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_restriction",
            "description": (
                "מסיר מהפרופיל הגבלת \"אל תקנה\" ששמורה בו. קרא לו רק אם המשתמש ביקש במפורש לבטל את ההגבלה. "
                "אם ההגבלה הייתה על סוג נכס, ההצעה והחלוקה החודשית חוזרות לתמהיל הרגיל עבורו."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "ההגבלה להסרה, כפי שהיא מופיעה ב-no_buy_symbols בפרופיל"},
                },
                "required": ["item"],
            },
        },
    },
]
PROFILE_TOOLS = {spec["function"]["name"] for spec in PROFILE_TOOL_SPECS}

TOOL_SPECS = [*PROFILE_TOOL_SPECS,
    {
        "type": "function",
        "function": {
            "name": "get_proposal",
            "description": (
                "מחזיר את ההצעה שהקוד בונה מהפרופיל (כמו כפתור \"קבל הצעה\"): קרן חירום וחובות (safety), "
                "תמהיל בסוגי נכסים להון הנזיל ולהפקדה החודשית (capital), מסלול לפנסיה ולהשתלמות (pension), "
                "מה חסר בפרופיל (missing) והנימוקים (reasons). ההצעה בסוגי נכסים בלבד."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_allocation",
            "description": (
                "מחלק סכום להשקעה החודש כמו בדף הניהול החודשי: קודם השלמת קרן החירום לכספית (emergency_amount), "
                "בניכוי מה שכבר הופנה אליה בדיווחים קודמים, והשאר לפי התמהיל (lines). לא שומר דיווח. "
                "סכום בשקלים: amount. אחוז מהנטו: percent_of_net, והקוד מחשב את הסכום מהנטו שבפרופיל. "
                "שלח אחד מהם בלבד, או אף אחד (ואז נלקחת ההפקדה החודשית מהפרופיל)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "סכום בשקלים להשקעה החודש. אם לא צוין, נלקחת ההפקדה החודשית מהפרופיל",
                    },
                    "percent_of_net": {
                        "type": "number",
                        "description": "אחוז מהנטו החודשי שבפרופיל, למשל 10 עבור 10%. הקוד מחשב את הסכום. "
                                       "אל תחשב סכום בעצמך ואל תשלח יחד עם amount",
                    },
                },
                "required": [],
            },
        },
    },
]


def tool_specs() -> list:
    """רשימת הכלים שהמודל רואה."""
    return list(TOOL_SPECS)


MAX_RESTRICTION_LENGTH = 60


def _restriction_item(args: dict) -> tuple[str | None, str | None]:
    """מנרמל את item מהמודל: (שם לשמירה, סוג נכס/קבוצה או None). סוג נכס וקבוצה נשמרים בשם הקנוני,
    סמל לטיני באותיות גדולות. מחזיר (None, None) אם הערך ריק או ארוך מדי."""
    item = " ".join(str(args.get("item") or "").split())
    if not item or len(item) > MAX_RESTRICTION_LENGTH:
        return None, None
    target = restriction_target(item)
    return target or (item.upper() if item.isascii() else item), target


def _restriction_text(item: str) -> str:
    return f"לא לקנות: {item}"


def _profile_status(profile: InvestorProfile) -> dict:
    missing = profile.missing_fields()
    return {"missing": missing, "next_field": missing[0] if missing else None, "complete": not missing}


# הגנה בקוד: "תמכור את המניות שלי" היא לא "אל תקנה". נמצא בסט ההערכה (evals/README.md): המודל שמר הגבלה
# "מניות" על בקשת מכירה, ושיפור הפרומפט לא עזר. לכן הקוד בודק את הודעת המשתמש עצמה.
SELL_WORDS = re.compile(r"(?:תמכור|תמכרי|תמכרו|למכור|נמכור|אמכור|מכור|מוכר|מוכרת|מוכרים|מכירה|מכירת|מכירות)")
NO_BUY_PHRASE = re.compile(
    r"(?:לא|אל|בלי|להפסיק|תפסיק|הפסק)\s+(?:\S+\s+){0,2}?"
    r"(?:לקנות|תקנה|תקני|תקנו|לרכוש|תרכוש|תרכשי|קונה|קונים|אקנה|נקנה|להשקיע|תשקיע)")
SELL_REJECTED = ("המשתמש ביקש למכור, וזו לא הגבלת \"אל תקנה\". בפרויקט אין המלצות מכירה והסוכן לא מבצע פעולות, "
                 "ולכן לא נשמרה הגבלה. הסבר זאת למשתמש. אם לא ברור אם הוא רוצה גם להפסיק לקנות, שאל אותו")


def is_sell_request(user_message: str | None) -> bool:
    """יש פועל מכירה בהודעה ואין ניסוח של "לא לקנות" / "אל תקנה". None (אין הודעה): לא בודקים."""
    if not user_message:
        return False
    return bool(SELL_WORDS.search(user_message)) and not NO_BUY_PHRASE.search(user_message)


def run_profile_tool(name: str, args: dict, profile: InvestorProfile, today: date | None = None,
                     user_message: str | None = None) -> tuple[dict, InvestorProfile]:
    """מריץ כלי שמשנה את הפרופיל. מחזיר (תוצאה למודל, פרופיל מעודכן). הפרופיל לא משתנה כשיש שגיאה.
    today משמש לחישוב אופק משנת יעד (ברירת מחדל: date.today()).
    user_message: ההודעה האחרונה של המשתמש בתור, כדי שהקוד יבדוק בעצמו מה נאמר (מכירה, "לא יודע").
    None: בלי הבדיקות האלה (קריאה ישירה, למשל מבדיקות)."""
    args = args if isinstance(args, dict) else {}

    if name == "update_profile":
        new_profile, accepted, rejected = apply_profile_update(profile, args, today, user_message)
        return {"accepted": accepted, "rejected": rejected, **_profile_status(new_profile)}, new_profile

    if name == "add_restriction":
        kind = args.get("kind") or "no_buy"
        if kind != "no_buy":
            return {"error": f"סוג מגבלה לא נתמך: {kind}. נתמך רק no_buy"}, profile
        if is_sell_request(user_message):
            return {"error": SELL_REJECTED, "saved": False}, profile
        item, asset_class = _restriction_item(args)
        if item is None:
            return {"error": f"חסר מה לא לקנות (עד {MAX_RESTRICTION_LENGTH} תווים), למשל TSLA"}, profile

        data = profile.model_dump()
        data["no_buy_symbols"] = list(dict.fromkeys([*data["no_buy_symbols"], item]))
        data["restrictions"] = list(dict.fromkeys([*data["restrictions"], _restriction_text(item)]))
        new_profile = InvestorProfile(**data)
        result = {"saved": True, "no_buy_symbols": new_profile.no_buy_symbols, "asset_class": asset_class,
                  "blocked_asset_classes": list(classes_blocked_by(item)),
                  "affects_proposal": asset_class is not None, **_profile_status(new_profile)}
        if asset_class is None:
            result["note"] = (f"{item} אינו סוג נכס. ההצעה והחלוקה החודשית הן לפי סוגי נכסים, "
                              "ולכן ההגבלה נשמרה אבל לא משנה אותן")
        return result, new_profile

    if name == "remove_restriction":
        item, asset_class = _restriction_item(args)
        if item is None or item not in profile.no_buy_symbols:
            return {"error": "לא נמצאה הגבלה כזו בפרופיל", "no_buy_symbols": profile.no_buy_symbols}, profile
        data = profile.model_dump()
        data["no_buy_symbols"] = [x for x in data["no_buy_symbols"] if x != item]
        data["restrictions"] = [r for r in data["restrictions"] if r != _restriction_text(item)]
        new_profile = InvestorProfile(**data)
        return {"removed": item, "no_buy_symbols": new_profile.no_buy_symbols,
                "affects_proposal": asset_class is not None, **_profile_status(new_profile)}, new_profile

    return {"error": f"כלי פרופיל לא מוכר: {name}"}, profile


def run_tool(name: str, args: dict, store, user_id: int, profile: InvestorProfile,
             today: date | None = None) -> dict:
    """מריץ כלי ומחזיר תוצאה כמילון. שגיאות חוזרות כ-{"error": ...} כדי שהסוכן יסביר אותן."""
    args = args if isinstance(args, dict) else {}
    try:
        if name == "get_proposal":
            return build_proposal(profile, today).model_dump(mode="json")

        if name == "get_monthly_allocation":
            amount, percent = args.get("amount"), args.get("percent_of_net")
            if amount is not None and percent is not None:
                return {"error": "שלח amount (שקלים) או percent_of_net (אחוז מהנטו), לא את שניהם"}
            percent_reason = None
            if percent is not None:
                amount, percent_reason = amount_from_percent_of_net(profile, percent)
            elif amount is None:
                amount = profile.monthly_deposit
            if amount is None:
                return {"error": "לא צוין סכום, ובפרופיל אין הפקדה חודשית"}
            already = emergency_deposited(store.list_salary_events(user_id, limit=ALL_HISTORY))
            result = allocate_monthly(profile, float(amount), today, already).model_dump(mode="json")
            if percent_reason:
                result["reasons"].insert(0, percent_reason)
                result["amount_from_percent"] = {"percent_of_net": float(percent),
                                                 "monthly_net_income": profile.monthly_net_income, "amount": amount}
            return result

        return {"error": f"כלי לא מוכר: {name}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"תקלה בהרצת הכלי: {e}"}
