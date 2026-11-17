"""חיבור הכלים לסוכן: הגדרות הכלים שה-LLM רואה, והפונקציה שמריצה אותם."""
from portfolio_copilot.plan import SavingsPlan
from portfolio_copilot.salary import plan_salary
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.tools import get_prices, plan_trades

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": "מחזיר את ההחזקות השמורות של המשתמש עם מחיר עדכני, שווי ומשקל של כל נכס בתיק.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_deposit",
            "description": (
                "מחשב הצעה להשקעה לפי רמת הסיכון שהמשתמש אישר: איך לחלק הפקדה חדשה (חד פעמית או חודשית). "
                "אם allow_sell=true, מציע גם אילו נכסים בודדים לצמצם (מכירה) כדי לעמוד בתקרת המשקל. "
                "כל התוצאה היא הצעה להחלטת המשתמש. הפעל allow_sell רק אם המשתמש ביקש או הסכים לשקול מכירה."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "סכום ההפקדה. אם לא צוין, נלקחת ההפקדה החודשית מהפרופיל. 0 מתאים לאיזון מחדש בלי כסף חדש."},
                    "allow_sell": {"type": "boolean", "description": "האם לכלול הצעות מכירה. ברירת מחדל false."},
                    "keep_symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "סימולים שהמשתמש אמר שהוא לא מוכר (לפי ה-restrictions בפרופיל), למשל [\"ZIM\"].",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_documents",
            "description": (
                "מחזיר נתונים שחולצו מהמסמכים שהמשתמש העלה. payslips: הכנסה נטו, הפרשות לפנסיה ולקרן השתלמות ומס שולי. "
                "fund_reports: דוחות רבעוניים מקופות גמל, השתלמות ופנסיה (יתרה, דמי ניהול מול ממוצע הקופה, מסלול ותשואה). "
                "warnings מציין מספרים שלא הסתדרו בבדיקה וכדאי לאמת מול המסמך."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_plan",
            "description": (
                "שומר את תוכנית החיסכון החודשית של המשתמש: כמה להפריש מכל משכורת, ולאן. התוכנית נגזרת ממה שהמשתמש סיפר "
                "(הכנסה, כמה הוא יכול להפריש, מטרות). user_confirmed=true רק אם המשתמש אישר את התוכנית במפורש בהודעה האחרונה."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_net_income": {"type": "number", "description": "הכנסה נטו חודשית אופיינית"},
                    "savings_mode": {"type": "string", "enum": ["fixed", "percent"], "description": "fixed: סכום קבוע בשקלים. percent: אחוז מהנטו"},
                    "savings_value": {"type": "number", "description": "שקלים (fixed) או שבר מהנטו, 0.25 הוא 25% (percent)"},
                    "buckets": {
                        "type": "array",
                        "description": "חלוקת הסכום שמופרש. סכום ה-share צריך להיות 1",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "kind": {"type": "string", "enum": ["cash", "invest"], "description": "cash: כסף נזיל (קרן חירום, מטרה קרובה). invest: השקעות"},
                                "share": {"type": "number", "description": "החלק היחסי, בין 0 ל-1"},
                            },
                            "required": ["name", "kind", "share"],
                        },
                    },
                    "rationale": {"type": "string", "description": "למה התוכנית מתאימה לאדם הזה"},
                    "user_confirmed": {"type": "boolean"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "salary_received",
            "description": (
                "מריץ את התוכנית החודשית כשנכנסה משכורת ומחזיר רשימת פעולות מוצעות לאישור. "
                "אם לא צוינו סכומים, לוקח אותם מהתלוש האחרון שהמשתמש העלה."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "net": {"type": "number", "description": "כמה נכנס נטו לחשבון הבנק"},
                    "pension": {"type": "number", "description": "הפרשה חודשית לפנסיה"},
                    "study_fund": {"type": "number", "description": "הפרשה חודשית לקרן השתלמות"},
                },
                "required": [],
            },
        },
    },
]


SEARCH_SPEC = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "חיפוש במסמכי הידע (לוחות עמלות, דמי ניהול, תקנונים, כללי מס). מחזיר קטעים רלוונטיים עם שם המסמך.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "השאלה או מילות החיפוש בעברית"}},
            "required": ["query"],
        },
    },
}


def tool_specs(has_kb: bool) -> list:
    """רשימת הכלים שהמודל רואה. חיפוש במסמכים נכלל רק אם יש מאגר ידע."""
    return [*TOOL_SPECS, SEARCH_SPEC] if has_kb else list(TOOL_SPECS)


def _prices_for(symbols, fetch):
    prices, errors = {}, []
    for s in symbols:
        try:
            prices[s] = get_prices([s], fetch)[s]
        except Exception:
            errors.append(s)
    return prices, errors


def run_tool(name: str, args: dict, store, user_id: int, profile: InvestorProfile, fetch=None, kb=None) -> dict:
    """מריץ כלי ומחזיר תוצאה כמילון. שגיאות חוזרות כ-{"error": ...} כדי שהסוכן יסביר אותן."""
    try:
        if name == "search_documents":
            if kb is None:
                return {"error": "מאגר המסמכים לא זמין"}
            query = (args.get("query") or "").strip()
            if not query:
                return {"error": "חסרה שאלת חיפוש"}
            passages = kb.search(query, k=4)
            if not passages:
                return {"passages": [], "message": "לא נמצאו מסמכים. ייתכן שמאגר הידע ריק"}
            return {"passages": passages}

        if name == "get_documents":
            slips = store.list_documents(user_id, "payslip")[:3]
            reports = store.list_documents(user_id, "fund_report")[:3]
            if not slips and not reports:
                return {"payslips": [], "fund_reports": [], "message": "המשתמש עדיין לא העלה מסמכים"}
            nets = [d["summary"]["net_to_bank"] for d in slips if d["summary"].get("net_to_bank") is not None]
            return {
                "payslips": [{**d["summary"], "warnings": d["warnings"]} for d in slips],
                "avg_net_to_bank": round(sum(nets) / len(nets), 2) if nets else None,
                "fund_reports": [{**d["summary"], "warnings": d["warnings"]} for d in reports],
            }

        if name == "propose_plan":
            previous = store.load_plan(user_id).model_dump()
            fields = ("monthly_net_income", "savings_mode", "savings_value", "buckets", "rationale")
            merged = {**previous, **{k: args[k] for k in fields if args.get(k) is not None}}
            merged["confirmed"] = bool(args.get("user_confirmed"))  # כל שינוי דורש אישור מחדש
            plan = SavingsPlan.model_validate(merged)
            store.save_plan(user_id, plan)
            return {"saved": True, "plan": plan.model_dump(), "ready_to_run": plan.is_ready()}

        if name == "salary_received":
            net, pension, study = args.get("net"), args.get("pension"), args.get("study_fund")
            slips = store.list_documents(user_id, "payslip")
            if slips:
                latest = slips[0]["summary"]
                net = latest.get("net_to_bank") if net is None else net
                pension = latest.get("pension_monthly_total") if pension is None else pension
                study = latest.get("study_fund_monthly_total") if study is None else study
            if not net:
                return {"error": "לא צוין סכום נטו ואין תלוש שמור שאפשר להשתמש בו"}
            holdings = store.list_holdings(user_id)
            prices, errors = _prices_for([h["symbol"] for h in holdings], fetch)
            if errors:
                return {"error": f"לא נמצאו מחירים עבור: {', '.join(errors)}"}
            result = plan_salary(profile, store.load_plan(user_id), holdings, prices,
                                 float(net), float(pension or 0), float(study or 0))
            store.add_salary_event(user_id, result)
            return result

        holdings = store.list_holdings(user_id)

        if name == "get_portfolio":
            if not holdings:
                return {"holdings": [], "message": "עדיין לא נטענו החזקות"}
            prices, errors = _prices_for([h["symbol"] for h in holdings], fetch)
            rows = []
            for h in holdings:
                if h["symbol"] in prices:
                    price = prices[h["symbol"]]
                    rows.append({"symbol": h["symbol"], "quantity": h["quantity"], "avg_cost": h["avg_cost"],
                                 "price": round(price, 2), "value": round(h["quantity"] * price, 2)})
            total = sum(r["value"] for r in rows)
            for r in rows:
                r["weight"] = round(r["value"] / total, 4) if total else 0.0
            return {"holdings": rows, "total_value": round(total, 2), "price_errors": errors}

        if name == "plan_deposit":
            amount = args.get("amount")
            if amount is None:
                amount = profile.monthly_deposit
            allow_sell = bool(args.get("allow_sell", False))
            if not amount and not allow_sell:
                return {"error": "לא צוין סכום הפקדה"}
            prices, errors = _prices_for([h["symbol"] for h in holdings], fetch)
            if errors:
                return {"error": f"לא נמצאו מחירים עבור: {', '.join(errors)}"}
            result = plan_trades(profile, holdings, prices, float(amount or 0),
                                 args.get("keep_symbols"), allow_sell)
            result["weights_before"] = {k: round(v, 4) for k, v in result["weights_before"].items()}
            result["weights_after"] = {k: round(v, 4) for k, v in result["weights_after"].items()}
            return result

        return {"error": f"כלי לא מוכר: {name}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"תקלה בהרצת הכלי: {e}"}