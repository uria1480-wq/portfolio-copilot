import gradio as gr
from pydantic import BaseModel, Field

# 1. מודלים (Pydantic)
class AssetTarget(BaseModel):
    ticker: str
    target_weight: float = Field(gt=0, le=1.0)

class DepositPlanRequest(BaseModel):
    deposit_amount: float = Field(gt=0)
    targets: list[AssetTarget]

# 2. לוגיקת החישוב (Mock כרגע)
def calculate_allocation(deposit_amount: float, spy_weight: float) -> str:
    if deposit_amount <= 0:
        return "שגיאה: יש להזין סכום הפקדה חיובי."
    
    # חישוב משקל האג"ח כמשלים ל-100%
    spy_w = spy_weight / 100.0
    bond_w = 1.0 - spy_w

    request = DepositPlanRequest(
        deposit_amount=deposit_amount,
        targets=[
            AssetTarget(ticker="S&P 500 ETF", target_weight=spy_w),
            AssetTarget(ticker="BOND ETF", target_weight=bond_w),
        ],
    )

    spy_alloc = round(request.deposit_amount * spy_w, 2)
    bond_alloc = round(request.deposit_amount * bond_w, 2)
    total = spy_alloc + bond_alloc

    output = f"""### תוצאת חלוקת הפקדה מוצעת:
* **סכום להפקדה:** {deposit_amount:,.2f} ₪
---
* **רכישת S&P 500 ETF ({spy_weight:.0f}%):** {spy_alloc:,.2f} ₪
* **רכישת BOND ETF ({100 - spy_weight:.0f}%):** {bond_alloc:,.2f} ₪
---
**סה"כ הוקצה:** {total:,.2f} ₪
*(הערה: חישוב ראשוני - פונקציות AI ואופטימיזציה יחוברו בהמשך)*
"""
    return output

# 3. ממשק Gradio
def main() -> None:
    with gr.Blocks(title="Portfolio Copilot") as demo:
        gr.Markdown("# 📈 Portfolio Copilot - ממשק ניהול תיק ראשוני")
        gr.Markdown("הזינו סכום להפקדה חודשית ואת יעד החלוקה המבוקש:")

        with gr.Row():
            deposit_input = gr.Number(label="סכום הפקדה חודשית (₪)", value=5000, precision=2)
            spy_slider = gr.Slider(
                minimum=0,
                maximum=100,
                value=80,
                step=5,
                label="אחוז הקצאה ל-S&P 500 (השאר יוקצה לאג\"ח)",
            )

        submit_btn = gr.Button("חשב חלוקה מומלצת", variant="primary")
        result_output = gr.Markdown(label="תוצאה")

        submit_btn.click(
            fn=calculate_allocation,
            inputs=[deposit_input, spy_slider],
            outputs=result_output,
        )

    demo.launch()

if __name__ == "__main__":
    main()