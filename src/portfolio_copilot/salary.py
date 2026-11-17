"""מנוע האירוע "נכנסה משכורת": מחשב בקוד מה לעשות עם הנטו, לפי התוכנית האישית של המשתמש."""
from datetime import datetime, timezone

from portfolio_copilot.plan import SavingsPlan
from portfolio_copilot.schemas import InvestorProfile
from portfolio_copilot.tools import plan_trades


def plan_salary(profile: InvestorProfile, plan: SavingsPlan, holdings: list[dict], prices: dict[str, float],
                net: float, pension: float = 0.0, study_fund: float = 0.0,
                keep_symbols: list[str] | None = None) -> dict:
    """מחזיר רשימת פעולות מוצעות לאישור. לא מבצע כלום ולא מוכר כלום.

    pension ו-study_fund הם ההפרשות החודשיות (כולל מעסיק). הן לא יוצאות מהנטו, ולכן הן רק נספרות בסיכום.
    """
    if not plan.is_ready():
        raise ValueError("התוכנית החודשית טרם אושרה")
    if net <= 0:
        raise ValueError("סכום הנטו חייב להיות חיובי")

    wanted = plan.savings_value if plan.savings_mode == "fixed" else net * plan.savings_value
    set_aside = round(min(wanted, net), 2)
    warnings = []
    if wanted > net:
        warnings.append("הסכום המתוכנן להפרשה גבוה מהנטו שנכנס, ולכן ההפרשה הוגבלה לנטו")

    amounts = [round(set_aside * b.share, 2) for b in plan.buckets]
    amounts[-1] = round(amounts[-1] + set_aside - sum(amounts), 2)  # תיקון עיגול, הסכום המחולק שווה בדיוק להפרשה

    actions, invest_total = [], 0.0
    for bucket, amount in zip(plan.buckets, amounts):
        if amount <= 0:
            continue
        if bucket.kind == "cash":
            actions.append({"type": "transfer", "bucket": bucket.name, "amount": amount})
        else:
            invest_total += amount

    trades = None
    if invest_total > 0:
        trades = plan_trades(profile, holdings, prices, round(invest_total, 2), keep_symbols, allow_sell=False)
        actions += [{"type": "buy", "symbol": s, "amount": a} for s, a in trades["buys"].items()]

    return {
        "period": datetime.now(timezone.utc).strftime("%Y-%m"),
        "net": round(net, 2),
        "set_aside": set_aside,
        "free_to_spend": round(net - set_aside, 2),
        "pension_contributions": round(pension or 0, 2),
        "study_fund_contributions": round(study_fund or 0, 2),
        "total_saved_this_month": round(set_aside + (pension or 0) + (study_fund or 0), 2),
        "actions": actions,
        "cap_breached": bool(trades and trades["cap_breached"]),
        "breaching_symbols": trades["breaching_symbols"] if trades else [],
        "warnings": warnings,
    }