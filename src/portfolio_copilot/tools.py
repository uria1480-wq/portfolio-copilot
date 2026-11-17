"""כלים שהסוכן יפעיל: טעינת החזקות, מחירי שוק, חלוקת הפקדה והצעות קניה/מכירה."""
import csv
import io
import math
from typing import Callable

from portfolio_copilot.schemas import InvestorProfile

# --- הנחות להדגמה (ניתנות לשינוי) ---
# תמהיל יעד לכל רמת סיכון, ונכסי ייצוג (קרנות סל אמריקאיות) לכל סוג נכס.
RISK_TEMPLATES = {
    "שמרני":   {"equity": 0.30, "bonds": 0.50, "cash": 0.20},
    "מאוזן":   {"equity": 0.60, "bonds": 0.30, "cash": 0.10},
    "אגרסיבי": {"equity": 0.85, "bonds": 0.10, "cash": 0.05},
}
UNIVERSE = {"equity": "VT", "bonds": "BND", "cash": "BIL"}


# --- 1. טעינת החזקות מקובץ CSV ---
def parse_holdings_csv(text: str) -> list[dict]:
    """קורא CSV עם העמודות symbol, quantity ואופציונלית avg_cost."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames:
        raise ValueError("הקובץ ריק")
    names = {n.strip().lower(): n for n in reader.fieldnames}
    if "symbol" not in names or "quantity" not in names:
        raise ValueError("חסרות עמודות: נדרשות symbol ו-quantity")

    holdings = []
    for i, row in enumerate(reader, start=2):  # שורה 1 היא הכותרת
        symbol = (row[names["symbol"]] or "").strip().upper()
        if not symbol:
            continue
        try:
            quantity = float(row[names["quantity"]])
            raw_cost = row.get(names["avg_cost"], "") if "avg_cost" in names else ""
            avg_cost = float(raw_cost) if raw_cost not in (None, "") else None
        except ValueError:
            raise ValueError(f"שורה {i}: ערך לא מספרי עבור {symbol}")
        if quantity < 0:
            raise ValueError(f"שורה {i}: כמות שלילית עבור {symbol}")
        holdings.append({"symbol": symbol, "quantity": quantity, "avg_cost": avg_cost})
    return holdings


# --- 2. מחירי שוק ---
def _yfinance_last_price(symbol: str) -> float:
    import yfinance as yf  # יבוא מאוחר, כדי שהבדיקות לא ידרשו רשת

    hist = yf.Ticker(symbol).history(period="5d")
    if hist.empty:
        raise ValueError(f"לא נמצא מחיר עבור {symbol}")
    return float(hist["Close"].iloc[-1])


def get_prices(symbols: list[str], fetch: Callable[[str], float] | None = None) -> dict[str, float]:
    fetch = fetch or _yfinance_last_price
    return {s: float(fetch(s)) for s in symbols}


def _check_inputs(profile: InvestorProfile, holdings: list[dict], prices: dict[str, float]) -> None:
    if not profile.is_complete():
        raise ValueError("הפרופיל טרם מאושר: חסרים נתונים או אישור רמת סיכון")
    missing = [h["symbol"] for h in holdings if h["symbol"] not in prices]
    if missing:
        raise ValueError(f"חסרים מחירים עבור: {', '.join(missing)}")


# --- 3. חלוקת הפקדה (בלי מכירות) ---
def allocate_deposit(profile: InvestorProfile, holdings: list[dict], prices: dict[str, float], deposit: float) -> dict:
    """מחלק הפקדה חדשה בלי למכור כלום, כך שהתיק יתקרב לתמהיל של רמת הסיכון שאושרה.

    הכסף החדש מופנה רק לנכסי היעד (UNIVERSE). החזקות אחרות, כמו ריכוז גבוה בנכס אחד,
    לא נמכרות: משקלן יורד ככל שההפקדות מצטברות, והמשתמש מחליט אם למכור.
    """
    import numpy as np
    from scipy.optimize import minimize

    _check_inputs(profile, holdings, prices)
    if deposit <= 0:
        raise ValueError("סכום ההפקדה חייב להיות חיובי")

    template = RISK_TEMPLATES[profile.recommended_risk_level]
    target = {UNIVERSE[k]: w for k, w in template.items()}

    values = {h["symbol"]: h["quantity"] * prices[h["symbol"]] for h in holdings}
    symbols = list(dict.fromkeys([*values, *target]))
    v = np.array([values.get(s, 0.0) for s in symbols])
    t = np.array([target.get(s, 0.0) for s in symbols])
    can_buy = np.array([s in target for s in symbols])

    total = v.sum() + deposit
    d = deposit / total  # עובדים בשברים כדי שהפותר יהיה יציב מספרית
    v_frac = v / total

    def loss(y):
        return float(np.sum((v_frac + y - t) ** 2))

    y0 = np.where(can_buy, d / can_buy.sum(), 0.0)
    result = minimize(
        loss, y0, method="SLSQP",
        bounds=[(0, d) if b else (0, 0) for b in can_buy],
        constraints=[{"type": "eq", "fun": lambda y: y.sum() - d}],
    )
    y = np.clip(result.x, 0, None)
    amounts = np.round(y / y.sum() * deposit, 2)
    amounts[np.argmax(amounts)] += round(deposit - amounts.sum(), 2)  # תיקון עיגול

    after = v + amounts
    w_before = {s: float(x) for s, x in zip(symbols, v / v.sum())} if v.sum() > 0 else {}
    w_after = {s: float(x) for s, x in zip(symbols, after / after.sum())}
    cap = profile.max_single_asset_weight or 0.20
    # התקרה חלה על נכסים בודדים, לא על קרנות הייצוג הרחבות של התמהיל
    breaching = [s for s, w in w_after.items() if s not in target and w > cap + 1e-9]

    return {
        "deposit_split": {s: float(a) for s, a in zip(symbols, amounts) if a > 0},
        "weights_before": w_before,
        "weights_after": w_after,
        "cap": cap,
        "cap_breached": bool(breaching),
        "breaching_symbols": breaching,
    }


# --- 4. הצעות קניה/מכירה (להחלטת המשתמש) ---
def plan_trades(profile: InvestorProfile, holdings: list[dict], prices: dict[str, float],
                deposit: float = 0.0, keep_symbols: list[str] | None = None, allow_sell: bool = False) -> dict:
    """מציע קניות ומכירות. ההחלטה הסופית תמיד אצל המשתמש.

    - נכס בודד שחורג מהתקרה מוצע למכירה עד התקרה (רק אם allow_sell=True).
    - נכסים ב-keep_symbols (שהמשתמש אמר שלא ימכור) לא מוצעים למכירה לעולם.
    - הכסף שהתפנה והפקדה חדשה מחולקים בין נכסי היעד לפי רמת הסיכון שאושרה.
    """
    _check_inputs(profile, holdings, prices)
    if deposit < 0:
        raise ValueError("סכום ההפקדה לא יכול להיות שלילי")
    if isinstance(keep_symbols, str):
        keep_symbols = [keep_symbols]
    keep = {s.strip().upper() for s in (keep_symbols or []) if s and s.strip()}

    cap = profile.max_single_asset_weight or 0.20
    universe = set(UNIVERSE.values())
    values = {h["symbol"]: h["quantity"] * prices[h["symbol"]] for h in holdings}
    total = sum(values.values()) + deposit
    if total <= 0:
        raise ValueError("אין החזקות ואין סכום להשקעה")

    sells = {}
    if allow_sell:
        for symbol, value in values.items():
            if symbol in universe or symbol in keep:
                continue
            excess = value - cap * total
            if excess > 0.01:
                sells[symbol] = math.ceil(excess * 100) / 100

    cash = round(deposit + sum(sells.values()), 2)
    buys = {}
    if cash > 0:
        reduced = [{**h, "quantity": max(0.0, h["quantity"] - sells.get(h["symbol"], 0.0) / prices[h["symbol"]])}
                   for h in holdings]
        buys = allocate_deposit(profile, reduced, prices, cash)["deposit_split"]

    symbols = list(dict.fromkeys([*values, *buys]))
    after = {s: values.get(s, 0.0) - sells.get(s, 0.0) + buys.get(s, 0.0) for s in symbols}
    after_total = sum(after.values())
    w_after = {s: after[s] / after_total for s in symbols}
    before_total = sum(values.values())
    w_before = {s: v / before_total for s, v in values.items()} if before_total > 0 else {}
    breaching = [s for s, w in w_after.items() if s not in universe and w > cap + 1e-6]

    return {
        "deposit": float(deposit),
        "buys": buys,
        "sells": [{"symbol": s, "amount": a, "approx_quantity": round(a / prices[s], 2)} for s, a in sells.items()],
        "cash_from_sales": round(sum(sells.values()), 2),
        "weights_before": w_before,
        "weights_after": w_after,
        "cap": cap,
        "cap_breached": bool(breaching),
        "breaching_symbols": breaching,
        "kept_symbols": sorted(keep & set(values)),
    }