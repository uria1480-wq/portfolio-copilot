"""בדיקת זמני תגובה של המודל, מחוץ לאפליקציה.

1. מדפיס את מזהי המודלים שהספק מחזיר ומסנן את אלה שמכילים flash.
2. מריץ על כל מודל כזה (עד 4) את הבקשה הרגילה 4 פעמים, ומדפיס חציון, מינימום, מקסימום וכמה ריצות נכשלו.
3. שולח את אותה בקשה (SYSTEM_PROMPT והודעת משתמש אחת, בלי כלים) בשלוש וריאציות, פעמיים כל אחת,
   ומדפיס לכל ריצה כמה שניות היא לקחה וכמה טוקנים נוצרו.

הרצה:  uv run python scripts/latency_check.py
הסקריפט שולח בקשות אמיתיות ל-API לפי ה-.env, ולכן צורך מכסה.
"""
import statistics
import sys
import time

from portfolio_copilot.agent import MODEL_NAME, SYSTEM_PROMPT, client

USER_MESSAGE = "אני בן 34, אופק 15 שנה"
SHORT_INSTRUCTION = "ענה ב-2 עד 3 משפטים קצרים"
REPEATS = 2
MAX_MODELS = 4
MODEL_RUNS = 4

VARIANTS = [
    ("1. baseline", SYSTEM_PROMPT, {}),
    ("2. reasoning_effort=low", SYSTEM_PROMPT, {"reasoning_effort": "low"}),
    ("3. short-answer instruction", f"{SYSTEM_PROMPT}\n{SHORT_INSTRUCTION}", {}),
]


def usage_numbers(usage) -> dict:
    """מוציא מה-usage את מספרי הטוקנים. שדה שהספק לא מחזיר יוצג כ-?"""
    if usage is None:
        return {"prompt": None, "completion": None, "reasoning": None, "total": None}
    details = getattr(usage, "completion_tokens_details", None)
    return {
        "prompt": getattr(usage, "prompt_tokens", None),
        "completion": getattr(usage, "completion_tokens", None),
        "reasoning": getattr(details, "reasoning_tokens", None) if details is not None else None,
        "total": getattr(usage, "total_tokens", None),
    }


def show(value) -> str:
    return "?" if value is None else str(value)


def run_once(system_prompt: str, extra: dict, model: str = MODEL_NAME) -> dict:
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        temperature=0.3,  # כמו ב-chat_step
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": USER_MESSAGE},
        ],
        **extra,
    )
    seconds = time.perf_counter() - started
    reply = (response.choices[0].message.content or "").strip()
    return {"seconds": seconds, "chars": len(reply), "reply": reply, **usage_numbers(response.usage)}


def flash_models() -> list[str]:
    """מדפיס את כל מזהי המודלים שהספק מחזיר, ומחזיר עד MAX_MODELS שמכילים flash.
    המודל הנוכחי של האפליקציה נבחר ראשון אם הוא ברשימה, כדי שתמיד תהיה נקודת השוואה."""
    try:
        ids = [m.id for m in client.models.list()]
    except Exception as e:
        print(f"models.list failed: {type(e).__name__}: {e}\n")
        return []
    print(f"=== models from provider ({len(ids)}) ===")
    for model_id in ids:
        print(f"  {model_id}")
    flash = [m for m in ids if "flash" in m.lower()]
    print(f"\n=== models containing 'flash' ({len(flash)}) ===")
    for model_id in flash:
        print(f"  {model_id}")
    if MODEL_NAME in flash:
        flash = [MODEL_NAME, *[m for m in flash if m != MODEL_NAME]]
    chosen = flash[:MAX_MODELS]
    print(f"\nwill test {len(chosen)}: {', '.join(chosen) or 'none'}\n")
    return chosen


def compare_models(models: list[str]) -> None:
    """הבקשה הרגילה (בלי reasoning_effort ובלי הוראת קיצור), MODEL_RUNS ריצות לכל מודל."""
    rows = []
    for model in models:
        print(f"=== {model} ===")
        times, failed = [], 0
        for attempt in range(1, MODEL_RUNS + 1):
            try:
                r = run_once(SYSTEM_PROMPT, {}, model)
            except Exception as e:
                failed += 1
                print(f"  run {attempt}: ERROR {type(e).__name__}: {str(e)[:200]}")
                continue
            times.append(r["seconds"])
            print(f"  run {attempt}: {r['seconds']:.2f}s | completion tokens={show(r['completion'])} "
                  f"reasoning={show(r['reasoning'])}")
        rows.append((model, times, failed))
        print()

    print("=== model comparison (seconds) ===")
    for model, times, failed in rows:
        if times:
            stats = (f"median={statistics.median(times):.2f} min={min(times):.2f} max={max(times):.2f}")
        else:
            stats = "no successful runs"
        print(f"  {model}: {stats} | failed {failed}/{MODEL_RUNS}")
    print()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # עברית בטרמינל של Windows
    except Exception:
        pass

    print(f"app model: {MODEL_NAME}")
    print(f"user message: {USER_MESSAGE}\n")

    compare_models(flash_models())

    print(f"### prompt variants on {MODEL_NAME} ###\n")
    summary = []

    for name, system_prompt, extra in VARIANTS:
        print(f"=== {name} ===")
        times = []
        for attempt in range(1, REPEATS + 1):
            try:
                r = run_once(system_prompt, extra)
            except Exception as e:  # למשל ספק שלא מכיר את reasoning_effort
                print(f"  run {attempt}: ERROR {type(e).__name__}: {e}")
                continue
            times.append(r["seconds"])
            print(f"  run {attempt}: {r['seconds']:.2f}s | tokens: completion={show(r['completion'])} "
                  f"reasoning={show(r['reasoning'])} prompt={show(r['prompt'])} total={show(r['total'])} "
                  f"| reply chars={r['chars']}")
            print(f"    reply: {r['reply'][:200].replace(chr(10), ' ')}")
        summary.append((name, times))
        print()

    print("=== summary (average seconds) ===")
    for name, times in summary:
        avg = f"{sum(times) / len(times):.2f}s" if times else "no successful runs"
        print(f"  {name}: {avg} ({len(times)}/{REPEATS} runs)")


if __name__ == "__main__":
    main()
