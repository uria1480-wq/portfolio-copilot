"""סוגי הנכסים והגבלות "אל תקנה X" (חוק 6): זיהוי סוג נכס או קבוצה מטקסט, ומעבר החלק האסור לתחליף.

קוד טהור, בלי מודל שפה. משמש את ההצעה (proposal.py), את החלוקה החודשית (monthly.py) ואת הכלים
add_restriction / remove_restriction (agent_tools.py). סמל ספציפי (כמו TSLA) לא חוסם סוג נכס.
"""
from portfolio_copilot.schemas import InvestorProfile

# מחלקות הנכסים, בסדר ההצגה
US_EQUITY = 'מדד מניות ארה"ב'
WORLD_EQUITY = "מדד מניות עולמי"
GOV_BONDS = 'אג"ח ממשלתי'
CORP_BONDS = 'אג"ח קונצרני'
MONEY_MARKET = "כספית"
ASSET_CLASSES = (US_EQUITY, WORLD_EQUITY, GOV_BONDS, CORP_BONDS, MONEY_MARKET)

# חוק 6: "אל תקנה X" על סוג נכס. החלק שלו עובר לתחליף המותר הראשון ברשימה:
# קודם הסוג הקרוב באותה קבוצה, ואם כל הקבוצה אסורה, לכספית. כספית אסורה עוברת לאג"ח ממשלתי.
SUBSTITUTES = {
    US_EQUITY: (WORLD_EQUITY, MONEY_MARKET, GOV_BONDS, CORP_BONDS),
    WORLD_EQUITY: (US_EQUITY, MONEY_MARKET, GOV_BONDS, CORP_BONDS),
    GOV_BONDS: (CORP_BONDS, MONEY_MARKET),
    CORP_BONDS: (GOV_BONDS, MONEY_MARKET),
    MONEY_MARKET: (GOV_BONDS, CORP_BONDS),
}
EQUITY_CLASSES = (US_EQUITY, WORLD_EQUITY)


# ניסוחים נפוצים לכל סוג נכס (אחרי נרמול: מירכאות ישרות, רווח אחד, אותיות לטיניות גדולות)
ASSET_CLASS_ALIASES = {
    US_EQUITY: ('מניות ארה"ב', 'מדד ארה"ב', 'מדד אמריקאי', "מניות אמריקאיות", "S&P 500", "S&P500", "SP500"),
    WORLD_EQUITY: ("מניות עולמיות", "מדד עולמי", "מניות עולם", "MSCI WORLD", "ACWI"),
    GOV_BONDS: ('אג"ח ממשלתיות', "אגרות חוב ממשלתיות", 'אג"ח מדינה', "ממשלתי", "ממשלתיות"),
    CORP_BONDS: ('אג"ח קונצרניות', "אגרות חוב קונצרניות", 'אג"ח חברות', "קונצרני", "קונצרניות"),
    MONEY_MARKET: ("קרן כספית", "קרנות כספיות", "כספיות"),
}


def _normalize_name(text: str) -> str:
    return " ".join(str(text).replace("״", '"').replace("“", '"').replace("”", '"').upper().split())


_ASSET_CLASS_LOOKUP = {_normalize_name(name): k for k, names in ASSET_CLASS_ALIASES.items() for name in (k, *names)}


def asset_class_of(item: str) -> str | None:
    """אם item הוא אחד מחמשת סוגי הנכסים או ניסוח מוכר שלו (ASSET_CLASS_ALIASES), מחזיר את השם הקנוני.
    בלי תלות ברווחים, בסוג המירכאות ובאותיות גדולות/קטנות. אחרת None."""
    return _ASSET_CLASS_LOOKUP.get(_normalize_name(item))


# הגבלה על קבוצה שלמה: "מניות" חוסם את שני מדדי המניות, "אג"ח" את שני סוגי האג"ח
EQUITY_GROUP = "מניות"
BOND_GROUP = 'אג"ח'
ASSET_GROUPS = {EQUITY_GROUP: EQUITY_CLASSES, BOND_GROUP: (GOV_BONDS, CORP_BONDS)}
GROUP_ALIASES = {
    EQUITY_GROUP: ("כל המניות", "שוק המניות", "מדדי מניות"),
    BOND_GROUP: ("אגח", "אגרות חוב", 'כל האג"ח'),
}
_GROUP_LOOKUP = {_normalize_name(name): g for g, names in GROUP_ALIASES.items() for name in (g, *names)}


def restriction_target(item: str) -> str | None:
    """השם הקנוני של מה ש-item חוסם: סוג נכס (ASSET_CLASSES) או קבוצה (ASSET_GROUPS). None לסמל ספציפי."""
    return asset_class_of(item) or _GROUP_LOOKUP.get(_normalize_name(item))


def classes_blocked_by(item: str) -> tuple[str, ...]:
    """סוגי הנכסים ש-item חוסם: אחד, שניים (קבוצה), או אף אחד (סמל ספציפי כמו TSLA)."""
    target = restriction_target(item)
    return ASSET_GROUPS.get(target, (target,)) if target else ()


def blocked_classes(profile: InvestorProfile) -> list[str]:
    """סוגי הנכסים שהמשתמש אמר שלא יקנה, בסדר ASSET_CLASSES. סמלים ספציפיים (כמו TSLA) לא נכללים."""
    blocked = {k for item in profile.no_buy_symbols for k in classes_blocked_by(item)}
    return [k for k in ASSET_CLASSES if k in blocked]


def substitute_for(asset_class: str, blocked: list[str]) -> str | None:
    """התחליף המותר הראשון לסוג נכס אסור, או None אם כל התחליפים אסורים."""
    return next((s for s in SUBSTITUTES[asset_class] if s not in blocked), None)


def blocked_groups(profile: InvestorProfile) -> list[str]:
    """הקבוצות שהמשתמש חסם במלואן ("מניות", "אג"ח"), בסדר ASSET_GROUPS."""
    targets = {restriction_target(item) for item in profile.no_buy_symbols}
    return [g for g in ASSET_GROUPS if g in targets]


def _group_reason(group: str, moves: dict[str, tuple[str | None, float]]) -> str:
    """הסבר אחד לקבוצה שנחסמה: אילו סוגים בה, ולאן עבר החלק שלהם."""
    classes = ASSET_GROUPS[group]
    head = f"ביקשת לא לקנות {group} ({' ו'.join(classes)})"
    by_target: dict[str | None, float] = {}
    for k in classes:
        target, share = moves[k]
        by_target[target] = round(by_target.get(target, 0.0) + share, 2)
    moved = {t: s for t, s in by_target.items() if t is not None and s}
    stuck = by_target.get(None, 0.0)
    parts = []
    if len(moved) == 1:
        [(t, s)] = moved.items()
        parts.append(f"ה-{s:g}% שלהן עברו ל{t}")
    elif moved:
        parts.append("החלק שלהן עבר כך: " + ", ".join(f"{s:g}% ל{t}" for t, s in moved.items()))
    if stuck:
        parts.append(f"{stuck:g}% נשארו בהן כי כל החלופות אסורות גם הן")
    return head + (", ולכן " + " ו".join(parts) if parts else "") + "."


def apply_restrictions(pct: dict[str, float], blocked: list[str],
                       groups: list[str] | tuple[str, ...] = ()) -> tuple[dict[str, float], list[str]]:
    """חוק 6: מעביר את האחוז של כל סוג נכס אסור לתחליף שלו. סכום האחוזים לא משתנה.
    מחזיר (אחוזים חדשים, הסברים). סוג נכס בלי תחליף מותר נשאר במקומו, עם הסבר.
    groups: קבוצות שנחסמו במלואן. לכל אחת הסבר אחד במקום הסבר לכל סוג נכס בה."""
    pct, reasons = dict(pct), []
    moves: dict[str, tuple[str | None, float]] = {}
    for k in blocked:
        share = pct[k]
        target = substitute_for(k, blocked)
        moves[k] = (target, share)
        if target is not None:
            pct[target] = round(pct[target] + share, 2)
            pct[k] = 0.0
    in_groups = {k for g in groups for k in ASSET_GROUPS[g]}
    reasons += [_group_reason(g, moves) for g in groups]
    for k in blocked:
        if k in in_groups:
            continue
        target, share = moves[k]
        if target is None:
            reasons.append(f"ביקשת לא לקנות {k}, אבל כל החלופות שלו אסורות גם הן, ולכן {share:g}% נשארו בו.")
        elif share:
            reasons.append(f"ביקשת לא לקנות {k}, ולכן ה-{share:g}% שלו עברו ל{target}.")
    return pct, reasons


def emergency_asset_class(blocked: list[str]) -> str:
    """לאן הולכת השלמת קרן החירום: כספית, ואם היא אסורה, התחליף שלה. אם אין תחליף מותר, נשארים בכספית."""
    if MONEY_MARKET not in blocked:
        return MONEY_MARKET
    return substitute_for(MONEY_MARKET, blocked) or MONEY_MARKET
