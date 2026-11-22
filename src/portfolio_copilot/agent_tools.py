"""חיבור הכלים לסוכן: הגדרות הכלים שה-LLM רואה, והפונקציה שמריצה אותם.
כל מספר שהסוכן מציג מגיע מכאן (proposal.py), לא מחישוב של המודל."""
from datetime import date

from portfolio_copilot.db import ALL_HISTORY
from portfolio_copilot.proposal import allocate_monthly, build_proposal, emergency_deposited
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
                    "max_single_asset_weight": {"type": "number", "description": "תקרת משקל לנכס בודד, 0.05 עד 1"},
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
                "שומר בפרופיל משהו שהמשתמש אמר שהוא לא רוצה לקנות: מניה, קרן או סוג נכס. "
                "המגבלה נרשמת ומוצגת בפרופיל. ההצעה והחלוקה החודשית לא מחושבות מחדש בעקבותיה."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "מה לא לקנות, כפי שהמשתמש אמר. למשל TSLA או אג\"ח קונצרני"},
                    "kind": {"type": "string", "enum": ["no_buy"], "description": "סוג המגבלה"},
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
                "בניכוי מה שכבר הופנה אליה בדיווחים קודמים, והשאר לפי התמהיל (lines). לא שומר דיווח."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "סכום בשקלים להשקעה החודש. אם לא צוין, נלקחת ההפקדה החודשית מהפרופיל",
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


def _profile_status(profile: InvestorProfile) -> dict:
    missing = profile.missing_fields()
    return {"missing": missing, "next_field": missing[0] if missing else None, "complete": not missing}


def run_profile_tool(name: str, args: dict, profile: InvestorProfile,
                     today: date | None = None) -> tuple[dict, InvestorProfile]:
    """מריץ כלי שמשנה את הפרופיל. מחזיר (תוצאה למודל, פרופיל מעודכן). הפרופיל לא משתנה כשיש שגיאה.
    today משמש לחישוב אופק משנת יעד (ברירת מחדל: date.today())."""
    args = args if isinstance(args, dict) else {}

    if name == "update_profile":
        new_profile, accepted, rejected = apply_profile_update(profile, args, today)
        return {"accepted": accepted, "rejected": rejected, **_profile_status(new_profile)}, new_profile

    if name == "add_restriction":
        kind = args.get("kind") or "no_buy"
        if kind != "no_buy":
            return {"error": f"סוג מגבלה לא נתמך: {kind}. נתמך רק no_buy"}, profile
        item = " ".join(str(args.get("item") or "").split())
        if not item or len(item) > MAX_RESTRICTION_LENGTH:
            return {"error": f"חסר מה לא לקנות (עד {MAX_RESTRICTION_LENGTH} תווים), למשל TSLA"}, profile
        item = item.upper() if item.isascii() else item

        data = profile.model_dump()
        data["no_buy_symbols"] = list(dict.fromkeys([*data["no_buy_symbols"], item]))
        data["restrictions"] = list(dict.fromkeys([*data["restrictions"], f"לא לקנות: {item}"]))
        new_profile = InvestorProfile(**data)
        return {"saved": True, "no_buy_symbols": new_profile.no_buy_symbols, **_profile_status(new_profile)}, new_profile

    return {"error": f"כלי פרופיל לא מוכר: {name}"}, profile


def run_tool(name: str, args: dict, store, user_id: int, profile: InvestorProfile,
             today: date | None = None) -> dict:
    """מריץ כלי ומחזיר תוצאה כמילון. שגיאות חוזרות כ-{"error": ...} כדי שהסוכן יסביר אותן."""
    args = args if isinstance(args, dict) else {}
    try:
        if name == "get_proposal":
            return build_proposal(profile, today).model_dump(mode="json")

        if name == "get_monthly_allocation":
            amount = args.get("amount")
            if amount is None:
                amount = profile.monthly_deposit
            if amount is None:
                return {"error": "לא צוין סכום, ובפרופיל אין הפקדה חודשית"}
            already = emergency_deposited(store.list_salary_events(user_id, limit=ALL_HISTORY))
            return allocate_monthly(profile, float(amount), today, already).model_dump(mode="json")

        return {"error": f"כלי לא מוכר: {name}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"תקלה בהרצת הכלי: {e}"}
